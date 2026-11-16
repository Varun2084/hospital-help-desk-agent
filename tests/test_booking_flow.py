"""Booking aur cancel: login kiya patient, Confirm button (backend jaanch), tareekh, beete slot, do log ek slot."""

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


ASHA, RAVI = "DEMO-ASHA", "DEMO-RAVI"


@pytest.fixture(autouse=True)
def registered_patients():
    """Do synthetic registered patient. Tests me 'login' = ctx ki state me patient ID (web app yahi karta hai)."""
    register_patient("Asha Verma", PHONE, patient_id=ASHA)
    register_patient("Ravi Kumar", "9123456789", patient_id=RAVI)
    return {"asha": ASHA, "ravi": RAVI}


def _request(time="09:00", patient=ASHA, **who):
    return request_booking("cardiology", MONDAY, time, make_ctx("09:00 book karna hai", patient=patient, **who))


def _confirm(pending, user="patient_001", session="s1", patient=ASHA) -> dict:
    """Patient ne card par Confirm dabaya: card ka action_id, fingerprint aur login ka patient backend ko jaate hain."""
    return confirm_pending(pending["action_id"], user, session, pending["fingerprint"], patient)


def _book(time="09:00", patient=ASHA, **who) -> dict:
    """Poora sahi raasta: model ki arzi, phir patient ka Confirm button."""
    pending = _request(time, patient, **who)
    return _confirm(pending, who.get("user", "patient_001"), who.get("session", "s1"), patient)


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
    assert _request(patient=RAVI)["status"] == "error"

    apt = booking["appointment_id"]
    assert request_cancellation(apt, make_ctx("cancel", patient=RAVI))["status"] == "error"   # Ravi ki nahin
    assert request_cancellation(apt, make_ctx("cancel"))["status"] == "login_required"
    pending = request_cancellation(apt, make_ctx("cancel karna hai", turn="turn-5", patient=ASHA))
    assert pending["status"] == "needs_confirmation" and _count() == 1
    done = _confirm(pending)
    assert done["status"] == "cancelled"
    assert "09:00" in check_available_slots("cardiology", MONDAY)["free_slots"]


def test_compact_date_cannot_bypass_a_booked_slot():
    """Review me mila: '20261116' likhne par booked slot khaali dikhta tha aur dobara book ho jaata tha."""
    _book()
    assert check_available_slots("cardiology", "20261116")["status"] == "error"
    compact = request_booking("cardiology", "20261116", "09:00", make_ctx(patient=RAVI))
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
    b = _request(patient=RAVI, user="patient_B", session="sB")
    results = []

    def confirm(pending, user, session, patient):
        results.append(_confirm(pending, user, session, patient))

    threads = [threading.Thread(target=confirm, args=(a, "patient_A", "sA", ASHA)),
               threading.Thread(target=confirm, args=(b, "patient_B", "sB", RAVI))]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(r["status"] for r in results) == ["booked", "error"]
    assert _count() == 1
    loser = next(r for r in results if r["status"] == "error")
    assert loser["free_slots"] and "09:00" not in loser["free_slots"]   # card par naye samay


def test_booking_needs_a_login_and_keeps_the_slot():
    """Bina login: arzi nahin banti, par chuna hua slot preview me lautta hai (login ke baad wahi)."""
    result = _request(patient=None)
    assert result["status"] == "login_required"
    assert result["preview"] == {"department": "Cardiology", "department_id": "cardiology", "date": MONDAY,
                                 "weekday": "Monday", "time": "09:00"}
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM pending_actions").fetchone()[0] == 0
    assert _request(patient=ASHA)["status"] == "needs_confirmation"


def test_booking_uses_the_logged_in_patient_not_the_chat():
    """Patient login se aata hai. Tool me naam ya phone ka argument hi nahin, isliye chat se badal nahin sakta."""
    pending = _request()
    assert pending["summary"]["patient_name"] == "Asha Verma" and "patient_id" not in pending["summary"]
    done = _confirm(pending)
    assert done["status"] == "booked"
    with db.connect() as conn:
        row = conn.execute("SELECT patient_ref, slot_id FROM appointments").fetchone()
    assert tuple(row) == (ASHA, "SLOT-cardiology-20261116-0900")


def test_only_the_same_login_can_press_confirm():
    """Asha ki arzi: logout ho chuka (None) ya Ravi ka login ho to Confirm kaam nahin karta."""
    pending = _request()
    assert _confirm(pending, patient=None)["status"] == "error"
    assert _confirm(pending, patient=RAVI)["status"] == "error"
    assert _count() == 0 and _confirm(pending)["status"] == "booked"


def test_registration_after_booking_is_not_repeated():
    """Screenshot me mila: appointment ke baad bhi naya registration ban gaya tha."""
    assert _book()["status"] == "booked"
    again = request_registration("asha verma", 34, "female", PHONE, "Rewa", make_ctx("register", turn="turn-9"))
    assert again["status"] == "already_registered" and again["patient_id"] == ASHA
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM patients WHERE phone = ?", (PHONE,)).fetchone()[0] == 1


def test_closed_department_cannot_be_booked():
    assert request_booking("dental", MONDAY, "09:00", make_ctx(patient=ASHA))["status"] == "error"
