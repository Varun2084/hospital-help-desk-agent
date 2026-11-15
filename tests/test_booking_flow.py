"""Booking aur cancel ke niyam: do kadam ki confirmation, tareekh, beete slot, do log ek slot."""

import threading
from datetime import datetime, timedelta

from conftest import FIXED_NOW, IST, make_ctx

from hospital_agent import db
from hospital_agent.tools import appointments
from hospital_agent.tools.appointments import (
    check_available_slots,
    confirm_action,
    request_booking,
    request_cancellation,
)

MONDAY = "2026-11-16"
PHONE = "9876543210"


def _request(time="09:00", name="Asha Verma", phone=PHONE, **who):
    return request_booking(name, phone, "cardiology", MONDAY, time, make_ctx("09:00 book karna hai", **who))


def _book(time="09:00", **who) -> dict:
    """Poora sahi raasta: arzi (turn-1), phir patient ka 'haan' (turn-2)."""
    pending = _request(time, **who)
    return confirm_action(pending["action_id"], make_ctx("haan, kar do", turn="turn-2", **who))


def _count() -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM appointments WHERE status = 'booked'").fetchone()[0]


def test_request_alone_books_nothing():
    pending = _request()
    assert pending["status"] == "needs_confirmation"
    assert pending["summary"]["phone"] == "98XXXXXX10"
    assert _count() == 0
    assert "09:00" in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_model_cannot_confirm_in_the_same_turn():
    """Model arzi banate hi usi turn me confirm bula de, to mana."""
    pending = _request()
    result = confirm_action(pending["action_id"], make_ctx("09:00 book karna hai", turn="turn-1"))
    assert result["status"] == "error" and _count() == 0


def test_confirm_needs_a_clear_yes_from_the_patient():
    pending = _request()
    for reply in ["ruko, 10 baje wala dekhte hain", "nahi", "hmm"]:
        result = confirm_action(pending["action_id"], make_ctx(reply, turn="turn-2"))
        assert result["status"] == "error", reply
    assert _count() == 0
    assert confirm_action(pending["action_id"], make_ctx("हाँ", turn="turn-3"))["status"] == "booked"


def test_another_patient_or_session_cannot_confirm():
    pending = _request()
    stranger = make_ctx("haan", turn="turn-2", user="patient_002")
    other_chat = make_ctx("haan", turn="turn-2", session="s2")
    assert confirm_action(pending["action_id"], stranger)["status"] == "error"
    assert confirm_action(pending["action_id"], other_chat)["status"] == "error"
    assert _count() == 0


def test_expired_action_is_rejected(monkeypatch):
    pending = _request()
    monkeypatch.setattr(appointments, "now", lambda: FIXED_NOW + timedelta(minutes=11))
    result = confirm_action(pending["action_id"], make_ctx("haan", turn="turn-2"))
    assert "samay nikal gaya" in result["message"] and _count() == 0


def test_retry_returns_same_booking_not_a_second_one():
    pending = _request()
    first = confirm_action(pending["action_id"], make_ctx("haan", turn="turn-2"))
    again = confirm_action(pending["action_id"], make_ctx("haan", turn="turn-3"))
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
    done = confirm_action(pending["action_id"], make_ctx("haan cancel kar do", turn="turn-6"))
    assert done["status"] == "cancelled"
    assert "09:00" in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_compact_date_cannot_bypass_a_booked_slot():
    """Review me mila: '20261116' likhne par booked slot khaali dikhta tha aur dobara book ho jaata tha."""
    _book()
    assert check_available_slots("cardiology", "20261116")["status"] == "error"
    assert request_booking("Ravi", "9123456789", "cardiology", "20261116", "09:00", make_ctx())["status"] == "error"
    assert _count() == 1


def test_same_day_past_slots_are_hidden_and_unbookable(monkeypatch):
    """Review me mila: 11:00 baje usi din ka 09:00 ka slot book ho jaata tha."""
    monkeypatch.setattr(appointments, "now", lambda: datetime(2026, 11, 16, 11, 0, tzinfo=IST))
    assert check_available_slots("cardiology", MONDAY)["free_slots"] == ["11:30"]
    assert _request("09:00")["status"] == "error"
    assert _request("11:30")["status"] == "needs_confirmation"


def test_slot_that_passes_while_waiting_is_not_booked(monkeypatch):
    monkeypatch.setattr(appointments, "now", lambda: datetime(2026, 11, 16, 8, 55, tzinfo=IST))
    pending = _request("09:00")
    monkeypatch.setattr(appointments, "now", lambda: datetime(2026, 11, 16, 9, 1, tzinfo=IST))
    assert confirm_action(pending["action_id"], make_ctx("haan", turn="turn-2"))["status"] == "error"
    assert _count() == 0


def test_two_patients_one_slot_only_one_wins():
    """Do alag patient ek hi slot ki arzi dete hain aur ek saath 'haan' kehte hain."""
    a = _request(user="patient_A", session="sA")
    b = _request(name="Ravi Kumar", phone="9123456789", user="patient_B", session="sB")
    results = []

    def confirm(pending, user, session):
        results.append(confirm_action(pending["action_id"], make_ctx("haan", "turn-2", user, session)))

    threads = [threading.Thread(target=confirm, args=(a, "patient_A", "sA")),
               threading.Thread(target=confirm, args=(b, "patient_B", "sB"))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r["status"] for r in results) == ["booked", "error"]
    assert _count() == 1


def test_closed_department_cannot_be_booked():
    assert request_booking("Asha", PHONE, "dental", MONDAY, "09:00", make_ctx())["status"] == "error"


def test_invalid_phone_is_rejected():
    assert "10 ankon" in _request(phone="12345")["message"]
