"""Release gate khud sahi pakadta hai? Har test backend me jaan-boojh kar ek galti daalta hai (sabotage) aur
dekhta hai ki eval suite wahi gate failure bataye. Gate kabhi pass na ho jab niyam toota ho.

Lesson 9 ke pehle teen: unauthorized record access, reschedule slot conflict, duplicate confirmation.
Saath me: confirmation bypass aur emergency.
"""

import pytest

from evals import runner
from hospital_agent import db, his
from hospital_agent.tools import common


def gate(case_id: str) -> list[str]:
    spec = next(c for c in runner.load_cases() if c["id"] == case_id)
    return runner.run_case(spec, "scripted", 1)["gate_failures"]


@pytest.mark.parametrize("case_id", ["records_cross_patient_request", "reschedule_roman_hindi_slot_taken",
                                     "booking_english_ortho_tomorrow_morning", "emergency_reviewed_phrase_no_booking",
                                     "notification_reprocessed_event_single_item"])
def test_suite_passes_on_the_real_backend(case_id):
    assert gate(case_id) == []


def test_gate_catches_unauthorized_record_access(monkeypatch):
    def any_owner(conn, patient_ref, test_id):   # galti: query me maalik (patient_ref) ki jaanch nahin
        return conn.execute("SELECT * FROM lab_tests WHERE id = ? AND report_released = 1", (test_id,)).fetchone()

    monkeypatch.setattr(db, "get_lab_report", any_owner)
    assert "cross_patient_disclosure" in gate("records_cross_patient_request")


def test_gate_catches_original_lost_on_slot_conflict(monkeypatch):
    real = his.LocalHIS.reschedule

    def careless(self, request_id, reference, patient_ref, expected_version, new_slot_id):
        try:
            return real(self, request_id, reference, patient_ref, expected_version, new_slot_id)
        except his.SlotTaken:
            self.cancel(reference, patient_ref)   # galti: naya slot nahin mila par purani booking hata di
            raise

    monkeypatch.setattr(his.LocalHIS, "reschedule", careless)
    assert "original_lost" in gate("reschedule_roman_hindi_slot_taken")


def test_gate_catches_duplicate_inbox_items(monkeypatch):
    real = db.insert_notification
    monkeypatch.setattr(db, "insert_notification", lambda conn, row: real(
        conn, {**row, "event_id": row["event_id"] + ":" + row["id"]}))   # galti: event_id se dedupe nahin
    assert "duplicate" in gate("notification_reprocessed_event_single_item")


def test_gate_catches_booking_without_confirmation(monkeypatch):
    real = common.create_pending_for

    def eager(kind, payload, *args):
        if kind == "book":
            his.get_his().book("EAGER-" + payload["slot_id"], payload["slot_id"], payload["patient_ref"])
        return real(kind, payload, *args)                                # galti: button se pehle hi booking

    monkeypatch.setattr(common, "create_pending_for", eager)
    assert "confirmation_bypass" in gate("booking_hindi_eye_tomorrow_morning")


def test_gate_catches_emergency_going_to_booking(monkeypatch):
    import web_app
    from hospital_agent import agent
    monkeypatch.setattr(web_app, "detect_risk", lambda text: None)         # galti: emergency jaanch hata di
    monkeypatch.setattr(agent, "emergency_guardrail", lambda **kwargs: None)
    assert "emergency_booking" in gate("emergency_reviewed_phrase_no_booking")
