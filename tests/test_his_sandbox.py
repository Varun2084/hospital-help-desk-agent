"""HIS adapter: sandbox par asli HTTP ke saath booking, takkar, timeout ke baad recovery aur HIS down."""

import threading

import httpx
import pytest
from conftest import make_ctx

from his_sandbox.server import SandboxServer
from hospital_agent import his
from hospital_agent.tools.actions import confirm_pending
from hospital_agent.tools.appointments import check_available_slots, request_booking, request_cancellation

MONDAY = "2026-11-16"


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    with SandboxServer(str(tmp_path / "his.db")) as server:
        monkeypatch.setenv("HIS_MODE", "sandbox")
        monkeypatch.setenv("HIS_URL", server.url)
        monkeypatch.setenv("HIS_TIMEOUT", "0.5")
        his._http_his.cache_clear()
        yield server
        httpx.post(f"{server.url}/_sandbox/faults", json={"lose_response_after_commit": 0, "delay_seconds": 0})
    his._http_his.cache_clear()


def _rows(server, time):
    return httpx.get(f"{server.url}/_sandbox/bookings",
                     params={"department_id": "cardiology", "date": MONDAY, "time": time}).json()


def _book(user, phone, time="09:00", name="Asha Verma"):
    pending = request_booking(name, phone, "cardiology", MONDAY, time, make_ctx("book", user=user, session=user))
    return pending, (lambda _turn: confirm_pending(pending["action_id"], user, user, pending["fingerprint"]))


def test_normal_booking_goes_to_his(sandbox):
    pending, confirm = _book("p1", "9876543210")
    assert pending["status"] == "needs_confirmation" and _rows(sandbox, "09:00") == []
    done = confirm("turn-2")
    assert done["status"] == "booked" and done["appointment_id"].startswith("HIS-")
    assert "09:00" not in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_competing_requests_only_one_wins(sandbox):
    _, confirm_a = _book("pa", "9876543210")
    _, confirm_b = _book("pb", "9123456780", name="Ravi Kumar")
    results = []
    threads = [threading.Thread(target=lambda f=f: results.append(f("turn-2"))) for f in (confirm_a, confirm_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r["status"] for r in results) == ["booked", "error"]
    assert len(_rows(sandbox, "09:00")) == 1


def test_timeout_after_commit_recovers_the_original_booking(sandbox):
    httpx.post(f"{sandbox.url}/_sandbox/faults", json={"lose_response_after_commit": 1, "delay_seconds": 2})
    _, confirm = _book("p1", "9876543210")
    first = confirm("turn-2")
    assert first["status"] == "in_progress"
    rows = _rows(sandbox, "09:00")
    assert len(rows) == 1                                   # HIS me booking ban chuki thi
    again = confirm("turn-3")
    assert again["status"] == "booked" and again["appointment_id"] == rows[0]["reference"]
    assert "nayi nahin bani" in again["note"]
    assert len(_rows(sandbox, "09:00")) == 1                # retry se doosri nahin bani
    assert confirm("turn-4") == again                       # aur retry: wahi jawab


def test_cancel_goes_to_his(sandbox):
    _, confirm = _book("p1", "9876543210")
    ref = confirm("turn-2")["appointment_id"]
    assert request_cancellation(ref, "9000000000", make_ctx("cancel", user="p1", session="p1"))["status"] == "error"
    pending = request_cancellation(ref, "9876543210", make_ctx("cancel", turn="turn-5", user="p1", session="p1"))
    done = confirm_pending(pending["action_id"], "p1", "p1", pending["fingerprint"])
    assert done["status"] == "cancelled" and _rows(sandbox, "09:00")[0]["status"] == "cancelled"
    assert "09:00" in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_sandbox_refuses_reusing_a_key_for_another_slot(sandbox):
    body = {"patient_name": "A", "phone": "9876543210", "department_id": "cardiology", "date": MONDAY}
    key = {"Idempotency-Key": "KEY-1"}
    first = httpx.post(f"{sandbox.url}/v1/bookings", json=body | {"time": "09:00"}, headers=key)
    again = httpx.post(f"{sandbox.url}/v1/bookings", json=body | {"time": "09:00"}, headers=key)
    other = httpx.post(f"{sandbox.url}/v1/bookings", json=body | {"time": "09:30"}, headers=key)
    assert (first.status_code, again.status_code, other.status_code) == (201, 200, 422)
    assert first.json()["reference"] == again.json()["reference"]


def test_his_down_gives_a_clear_message(monkeypatch):
    from his_sandbox.server import free_port
    monkeypatch.setenv("HIS_MODE", "sandbox")
    monkeypatch.setenv("HIS_URL", f"http://127.0.0.1:{free_port()}")   # yahan koi server nahin
    his._http_his.cache_clear()
    result = check_available_slots("cardiology", MONDAY)
    his._http_his.cache_clear()
    assert result["status"] == "error" and "system abhi jawab nahin" in result["message"]


def test_local_his_also_recovers_after_a_lost_response(monkeypatch):
    """Local mode me bhi wahi niyam: booking ho gayi, jawab kho gaya, retry par wahi booking."""
    real_book = his.LocalHIS.book
    calls = []

    def lose_first_response(self, *args):
        booking = real_book(self, *args)
        calls.append(booking.reference)
        if len(calls) == 1:
            raise his.HISTimeout("simulated")
        return booking

    monkeypatch.setattr(his.LocalHIS, "book", lose_first_response)
    _, confirm = _book("p1", "9876543210")
    assert confirm("turn-2")["status"] == "in_progress"
    again = confirm("turn-3")
    assert again["status"] == "booked" and again["appointment_id"] == calls[0] and len(calls) == 1
