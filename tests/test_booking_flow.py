"""Booking aur cancel ke niyam: Confirm button (backend jaanch), tareekh, beete slot, do log ek slot."""

import threading
from datetime import datetime, timedelta

import pytest
from conftest import FIXED_NOW, IST, make_ctx, register_patient

from hospital_agent import db
from hospital_agent.tools import FEATURE_TOOLS, common
from hospital_agent.tools.actions import confirm_pending, discard_pending
from hospital_agent.tools.appointments import (
    check_available_slots,
    request_booking,
    request_cancellation,
)
from hospital_agent.tools.registration import request_registration

MONDAY = "2026-11-16"
PHONE = "9876543210"


@pytest.fixture(autouse=True)
def registered_patients():
    """Booking sirf registered patient ki: do synthetic patient pehle se registered."""
    return {"asha": register_patient("Asha Verma", PHONE), "ravi": register_patient("Ravi Kumar", "9123456789")}


def _request(time="09:00", name="Asha Verma", phone=PHONE, **who):
    return request_booking(name, phone, "cardiology", MONDAY, time, make_ctx("09:00 book karna hai", **who))


def _confirm(pending, user="patient_001", session="s1") -> dict:
    """Patient ne card par Confirm dabaya: card ka action_id aur fingerprint backend ko jaate hain."""
    return confirm_pending(pending["action_id"], user, session, pending["fingerprint"])


def _book(time="09:00", **who) -> dict:
    """Poora sahi raasta: model ki arzi, phir patient ka Confirm button."""
    pending = _request(time, **who)
    return _confirm(pending, who.get("user", "patient_001"), who.get("session", "s1"))


def _count() -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM appointments WHERE status = 'booked'").fetchone()[0]


def test_request_alone_books_nothing():
    pending = _request()
    assert pending["status"] == "needs_confirmation"
    assert pending["summary"]["phone"] == "98XXXXXX10"
    assert _count() == 0
    assert "09:00" in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_model_has_no_tool_that_confirms():
    """Model ke paas pakka karne ka koi tool hi nahin: chat me 'ok' ya 'haan' likhne se kuch nahin hota."""
    names = {t.__name__ for tools in FEATURE_TOOLS.values() for t in tools}
    assert not any("confirm" in n for n in names)


def test_card_must_match_the_exact_request():
    """Card par jo details dikhi, wahi pakki hongi: fingerprint alag ho to mana."""
    pending = _request()
    result = confirm_pending(pending["action_id"], "patient_001", "s1", "0" * 16)
    assert result["status"] == "error" and _count() == 0
    assert _confirm(pending)["status"] == "booked"


def test_discard_removes_only_the_draft():
    pending = _request()
    assert discard_pending(pending["action_id"], "patient_001", "s1")["status"] == "discarded"
    assert _confirm(pending)["status"] == "discarded" and _count() == 0     # baad me Confirm se kuch nahin
    booked = _book("09:30")
    other = _request("10:00")
    _confirm(other)
    assert discard_pending(other["action_id"], "patient_001", "s1")["status"] == "booked"   # pakki ho chuki
    assert booked["status"] == "booked" and _count() == 2


def test_another_patient_or_session_cannot_confirm():
    pending = _request()
    assert _confirm(pending, user="patient_002")["status"] == "error"
    assert _confirm(pending, session="s2")["status"] == "error"
    assert discard_pending(pending["action_id"], "patient_002", "s1")["status"] == "error"
    assert _count() == 0


def test_expired_action_is_rejected(monkeypatch):
    pending = _request()
    monkeypatch.setattr(common, "now", lambda: FIXED_NOW + timedelta(minutes=11))
    result = _confirm(pending)
    assert "samay nikal gaya" in result["message"] and _count() == 0


def test_retry_returns_same_booking_not_a_second_one():
    pending = _request()
    first = _confirm(pending)
    again = _confirm(pending)          # button do baar dab gaya
    assert first["status"] == "booked" and again == first and _count() == 1


def test_book_then_slot_disappears_then_cancel():
    booking = _book()
    assert booking["status"] == "booked" and booking["phone"] == "98XXXXXX10"
    assert "09:00" not in check_available_slots("cardiology", MONDAY)["free_slots"]
    assert _request(name="Ravi Kumar", phone="9123456789")["status"] == "error"

    apt = booking["appointment_id"]
    assert request_cancellation(apt, "9000000000", make_ctx("cancel"))["status"] == "error"
    pending = request_cancellation(apt, PHONE, make_ctx("cancel karna hai", turn="turn-5"))
    assert pending["status"] == "needs_confirmation" and _count() == 1
    done = _confirm(pending)
    assert done["status"] == "cancelled"
    assert "09:00" in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_compact_date_cannot_bypass_a_booked_slot():
    """Review me mila: '20261116' likhne par booked slot khaali dikhta tha aur dobara book ho jaata tha."""
    _book()
    assert check_available_slots("cardiology", "20261116")["status"] == "error"
    compact = request_booking("Ravi Kumar", "9123456789", "cardiology", "20261116", "09:00", make_ctx())
    assert compact["status"] == "error"
    assert _count() == 1


def test_same_day_past_slots_are_hidden_and_unbookable(monkeypatch):
    """Review me mila: 11:00 baje usi din ka 09:00 ka slot book ho jaata tha."""
    monkeypatch.setattr(common, "now", lambda: datetime(2026, 11, 16, 11, 0, tzinfo=IST))
    assert check_available_slots("cardiology", MONDAY)["free_slots"] == ["11:30"]
    assert _request("09:00")["status"] == "error"
    assert _request("11:30")["status"] == "needs_confirmation"


def test_slot_that_passes_while_waiting_is_not_booked(monkeypatch):
    monkeypatch.setattr(common, "now", lambda: datetime(2026, 11, 16, 8, 55, tzinfo=IST))
    pending = _request("09:00")
    monkeypatch.setattr(common, "now", lambda: datetime(2026, 11, 16, 9, 1, tzinfo=IST))
    assert _confirm(pending)["status"] == "error"
    assert _count() == 0


def test_two_patients_one_slot_only_one_wins():
    """Do alag patient ek hi slot ki arzi dete hain aur ek saath Confirm dabate hain."""
    a = _request(user="patient_A", session="sA")
    b = _request(name="Ravi Kumar", phone="9123456789", user="patient_B", session="sB")
    results = []

    def confirm(pending, user, session):
        results.append(_confirm(pending, user, session))

    threads = [threading.Thread(target=confirm, args=(a, "patient_A", "sA")),
               threading.Thread(target=confirm, args=(b, "patient_B", "sB"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r["status"] for r in results) == ["booked", "error"]
    assert _count() == 1
    loser = next(r for r in results if r["status"] == "error")
    assert loser["free_slots"] and "09:00" not in loser["free_slots"]   # card par naye samay


def test_unregistered_patient_cannot_book():
    """Pehle registration, phir appointment: bina registration ke arzi bhi nahin banti."""
    result = _request(name="Naya Patient", phone="9988776655")
    assert result["status"] == "not_registered" and "registration" in result["message"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0] == 0


def test_booking_uses_the_registered_patient_id(registered_patients):
    pending = _request(name="  asha   VERMA ")          # naam me chhote-bade akshar aur space ka farq nahin
    assert pending["summary"]["patient_id"] == registered_patients["asha"]
    assert pending["summary"]["patient_name"] == "Asha Verma"
    done = _confirm(pending)
    assert done["patient_id"] == registered_patients["asha"]
    with db.connect() as conn:
        row = conn.execute("SELECT patient_ref, slot_id FROM appointments").fetchone()
    assert tuple(row) == (registered_patients["asha"], "SLOT-cardiology-20261116-0900")


def test_registration_after_booking_is_not_repeated(registered_patients):
    """Screenshot me mila: appointment ke baad bhi naya registration ban gaya tha."""
    assert _book()["status"] == "booked"
    again = request_registration("asha verma", 34, "female", PHONE, "Rewa", make_ctx("register", turn="turn-9"))
    assert again["status"] == "already_registered" and again["patient_id"] == registered_patients["asha"]
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM patients WHERE phone = ?", (PHONE,)).fetchone()[0] == 1


def test_closed_department_cannot_be_booked():
    assert request_booking("Asha Verma", PHONE, "dental", MONDAY, "09:00", make_ctx())["status"] == "error"


def test_invalid_phone_is_rejected():
    assert "10 ankon" in _request(phone="12345")["message"]
