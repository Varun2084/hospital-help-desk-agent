"""Fake HIS (alag server) aur adapter: teen endpoints, booking, takkar, timeout ke baad recovery aur HIS down."""

import threading

import httpx
import pytest
from conftest import make_ctx, register_patient

from his_sandbox.server import SandboxServer
from hospital_agent import his
from hospital_agent.tools.actions import confirm_pending
from hospital_agent.tools.appointments import (
    check_available_slots,
    request_booking,
    request_cancellation,
)

MONDAY = "2026-11-16"
SLOT_0900 = "SLOT-cardiology-20261116-0900"


ASHA, RAVI = "DEMO-ASHA", "DEMO-RAVI"


@pytest.fixture(autouse=True)
def registered_patients():
    register_patient("Asha Verma", "9876543210", patient_id=ASHA)
    register_patient("Ravi Kumar", "9123456780", patient_id=RAVI)


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


def _rows(server, slot_id=SLOT_0900):
    return httpx.get(f"{server.url}/_sandbox/bookings", params={"slot_id": slot_id}).json()


def _book(user, patient=ASHA, time="09:00"):
    pending = request_booking("cardiology", MONDAY, time, make_ctx("book", user=user, session=user, patient=patient))
    return pending, (lambda _turn: confirm_pending(pending["action_id"], user, user, pending["fingerprint"], patient))


def test_normal_booking_goes_to_his(sandbox):
    pending, confirm = _book("p1")
    assert pending["status"] == "needs_confirmation" and _rows(sandbox) == []
    done = confirm("turn-2")
    assert done["status"] == "booked" and done["appointment_id"] == "HIS-APT-001"   # scheduler ka reference
    assert "09:00" not in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_competing_requests_only_one_wins(sandbox):
    _, confirm_a = _book("pa")
    _, confirm_b = _book("pb", RAVI)
    results = []
    threads = [threading.Thread(target=lambda f=f: results.append(f("turn-2"))) for f in (confirm_a, confirm_b)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r["status"] for r in results) == ["booked", "error"]
    assert len(_rows(sandbox)) == 1


def test_timeout_after_commit_recovers_the_original_booking(sandbox):
    httpx.post(f"{sandbox.url}/_sandbox/faults", json={"lose_response_after_commit": 1, "delay_seconds": 2})
    _, confirm = _book("p1")
    first = confirm("turn-2")
    assert first["status"] == "in_progress"
    rows = _rows(sandbox)
    assert len(rows) == 1                                   # HIS me booking ban chuki thi
    again = confirm("turn-3")
    assert again["status"] == "booked" and again["appointment_id"] == rows[0]["booking_ref"]
    assert "nayi nahin bani" in again["note"]
    assert len(_rows(sandbox)) == 1                # retry se doosri nahin bani
    assert confirm("turn-4") == again                       # aur retry: wahi jawab


def test_cancel_goes_to_his(sandbox):
    _, confirm = _book("p1")
    ref = confirm("turn-2")["appointment_id"]
    assert request_cancellation(ref, make_ctx("cancel", user="p1", session="p1", patient=RAVI))["status"] == "error"
    pending = request_cancellation(ref, make_ctx("cancel", turn="turn-5", user="p1", session="p1", patient=ASHA))
    done = confirm_pending(pending["action_id"], "p1", "p1", pending["fingerprint"], ASHA)
    assert done["status"] == "cancelled" and _rows(sandbox)[0]["status"] == "cancelled"
    assert "09:00" in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_the_three_scheduler_endpoints(sandbox):
    """Lesson 3 ka contract: GET /v1/slots, POST /v1/bookings, GET /v1/bookings/by-request/{request_id}."""
    slots = httpx.get(f"{sandbox.url}/v1/slots", params={"department_id": "cardiology", "date": MONDAY}).json()
    assert slots["slots"][0] == {"slot_id": SLOT_0900, "time": "09:00", "status": "open"}
    body = {"slot_id": SLOT_0900, "patient_ref": "DEMO-PATIENT-001", "request_id": "BOOK-REQ-001"}
    first = httpx.post(f"{sandbox.url}/v1/bookings", json=body)
    assert first.status_code == 201
    assert first.json()["status"] == "confirmed"
    assert first.json()["booking_ref"] == "HIS-APT-001" and first.json()["slot_id"] == SLOT_0900
    again = httpx.post(f"{sandbox.url}/v1/bookings", json=body)                       # wahi attempt dobara
    other = httpx.post(f"{sandbox.url}/v1/bookings", json=body | {"request_id": "BOOK-REQ-002",
                                                                  "patient_ref": "DEMO-PATIENT-002"})
    reused = httpx.post(f"{sandbox.url}/v1/bookings", json=body | {"slot_id": "SLOT-cardiology-20261116-0930"})
    unknown = httpx.post(f"{sandbox.url}/v1/bookings", json=body | {"request_id": "BOOK-REQ-003",
                                                                    "slot_id": "SLOT-cardiology-20261116-0715"})
    assert (again.status_code, other.status_code, reused.status_code, unknown.status_code) == (200, 409, 422, 409)
    assert again.json()["booking_ref"] == "HIS-APT-001" and other.json()["status"] == "slot_unavailable"
    found = httpx.get(f"{sandbox.url}/v1/bookings/by-request/BOOK-REQ-001")
    assert found.status_code == 200 and found.json()["booking_ref"] == "HIS-APT-001"
    assert httpx.get(f"{sandbox.url}/v1/bookings/by-request/BOOK-REQ-404").status_code == 404
    left = httpx.get(f"{sandbox.url}/v1/slots", params={"department_id": "cardiology", "date": MONDAY}).json()
    assert SLOT_0900 not in {x["slot_id"] for x in left["slots"]}


def test_patient_records_are_scoped_in_the_his(sandbox):
    """HIS adapter bhi patient ke hisaab se: Ravi ke reference par Asha ko kuch nahin milta (generic 404)."""
    ref_a = _book("pa")[1]("t")["appointment_id"]
    ref_r = _book("pr", RAVI, time="09:30")[1]("t")["appointment_id"]
    system = his.get_his()
    assert [b.reference for b in system.list_for_patient(ASHA)] == [ref_a]
    assert system.find_for_patient(ASHA, ref_a).time == "09:00"
    assert system.find_for_patient(ASHA, ref_r) is None and system.find_for_patient(ASHA, "HIS-APT-999") is None
    assert httpx.get(f"{sandbox.url}/v1/patients/{ASHA}/bookings/{ref_r}").status_code == 404


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
        booking = real_book(self, *args)   # LocalHIS me booking ban gayi...
        calls.append(booking.reference)
        if len(calls) == 1:
            raise his.HISTimeout("simulated")
        return booking

    monkeypatch.setattr(his.LocalHIS, "book", lose_first_response)
    _, confirm = _book("p1")
    assert confirm("turn-2")["status"] == "in_progress"
    again = confirm("turn-3")
    assert again["status"] == "booked" and again["appointment_id"] == calls[0] and len(calls) == 1
