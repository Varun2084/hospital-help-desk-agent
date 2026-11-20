"""Lesson 8: patient notifications. Pakka nateeja + outbox event ek transaction me; worker inbox tak;
ek event = ek inbox item.

Sprint ke acceptance tests:
  1. Reception ne request claim ki, nateeja abhi baaki: patient ko koi 'resolved' ya 'updated' nahin
  2. Scheduler ne badlaav confirm kiya: inbox me ek notification, link updated appointment kholta hai
  3. Worker same event do baar chalaye: inbox me ek hi item
  4. Event save hone ke baad worker restart (ya beech me ruka): pending event baad me pahunchta hai
  5. Patient B, Patient A ki notification ka link khole: A ka kuch disclose nahin
  6. Reminder tay tha aur appointment cancel ho gayi: worker abhi ki haalat dekh kar purana reminder chhodta hai
"""

from datetime import timedelta

import pytest
from conftest import FIXED_NOW, make_ctx, register_patient
from fastapi.testclient import TestClient
from google.adk.sessions import InMemorySessionService
from test_reception import FRIDAY, MONDAY, PHONE_A, STAFF, handover, patient_client, slot, staff_client

from hospital_agent import db, his, notifications, records
from hospital_agent.tools.actions import confirm_pending
from hospital_agent.tools.appointments import request_booking
from web_app import create_app

A, B = "DEMO-PATIENT-A", "DEMO-PATIENT-B"


@pytest.fixture
def ref():
    """A registered (Monday 09:00 Cardiology), reception staff bhi. A ka booking reference."""
    register_patient("Demo Patient A", PHONE_A, patient_id=A)
    with db.connect() as conn:
        for sid, phone in STAFF.items():
            db.save_staff(conn, sid, f"Demo {sid[-1]}", phone)
    return his.get_his().book("SEED-A", slot(MONDAY, "09:00"), A).reference


def outbox(event_type=None):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM notification_outbox ORDER BY created_at").fetchall()
    return [r for r in rows if event_type is None or r["event_type"] == event_type]


def inbox_count(patient=A):
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM patient_notifications WHERE patient_ref = ?",
                            (patient,)).fetchone()[0]


def resolved_by_reception(ref, monkeypatch):
    """Lesson 8 ka pehla workflow: reschedule request reception ne 'apply' ki (scheduler ne confirm kiya)."""
    patient = patient_client()
    item_id = handover(patient, ref, monkeypatch)
    staff = staff_client()
    staff.post(f"/api/staff/queue/{item_id}/claim")
    done = staff.post(f"/api/staff/queue/{item_id}/resolve", json={"decision": "apply"}).json()
    assert done["resolution"] == "changed"
    return patient, item_id


def test_1_claimed_but_not_resolved_sends_nothing(ref, monkeypatch):
    patient = patient_client()
    item_id = handover(patient, ref, monkeypatch)
    staff_client().post(f"/api/staff/queue/{item_id}/claim")
    notifications.run_once()
    assert outbox() == [] and inbox_count() == 0
    assert patient.get("/api/me/notifications").json() == {"notifications": [], "unread": 0}


def test_2_confirmed_change_gives_one_notification_that_opens_the_updated_appointment(ref, monkeypatch):
    patient, _ = resolved_by_reception(ref, monkeypatch)
    assert inbox_count() == 0                                              # abhi sirf outbox me (worker baaki)
    assert [r["event_type"] for r in outbox()] == ["appointment.rescheduled", "appointment.reminder"]
    results = notifications.run_once()
    assert [r["status"] for r in results] == ["delivered"]                 # reminder Thursday ko, abhi nahin
    box = patient.get("/api/me/notifications").json()
    assert box["unread"] == 1 and len(box["notifications"]) == 1
    item = box["notifications"][0]
    assert item["body"]["hi"] == "आपकी अपॉइंटमेंट अपडेट हो गई है।"
    assert item["body"]["en"] == "Your appointment has been updated."
    assert FRIDAY not in str(item) and "10:00" not in str(item)          # sandesh generic; details dashboard me
    assert item["destination"] == {"view": "appointment", "id": ref} and item["link"] == f"/?open=appointment:{ref}"
    opened = patient.get(f"/api/me/appointments/{ref}").json()             # link wahi protected record kholta hai
    assert (opened["date"], opened["time"]) == (FRIDAY, "10:00")
    assert patient.post(f"/api/me/notifications/{item['id']}/read").json()["read"] is True
    assert patient.get("/api/me/notifications").json()["unread"] == 0


def test_3_processing_the_same_event_twice_keeps_one_inbox_item(ref, monkeypatch):
    resolved_by_reception(ref, monkeypatch)
    first = notifications.run_once()[0]
    again = notifications.replay(first["event_id"])
    assert again["status"] == "delivered" and again["created"] is False
    assert again["notification_id"] == first["notification_id"] and inbox_count() == 1
    assert notifications.run_once() == []                                  # delivered event dobara nahin uthta


def test_4_event_survives_a_worker_restart(ref, monkeypatch):
    resolved_by_reception(ref, monkeypatch)
    # Worker ne event uthaya, inbox me likha, aur 'delivered' likhne se pehle process band ho gaya
    with db.connect() as conn:
        claimed = db.claim_due_events(conn, FIXED_NOW.isoformat(), (FIXED_NOW + notifications.LEASE).isoformat(), 1)
    notifications.deliver_in_app(claimed[0])
    assert notifications.run_once() == []                                  # lease ke andar koi aur nahin uthata
    later = FIXED_NOW + notifications.LEASE + timedelta(seconds=1)         # naya worker (restart ke baad)
    results = notifications.run_once(later)
    assert [r["status"] for r in results] == ["delivered"] and results[0]["created"] is False
    assert inbox_count() == 1


def test_4b_event_saved_before_any_worker_ran_is_delivered_after_restart(ref, monkeypatch):
    resolved_by_reception(ref, monkeypatch)                                # app band: worker kabhi nahin chala
    app = create_app(session_service=InMemorySessionService())             # naya process
    with TestClient(app):                                                  # lifespan: worker shuru
        import time
        for _ in range(50):
            if inbox_count() == 1:
                break
            time.sleep(0.1)
    assert inbox_count() == 1


def test_5_patient_b_cannot_open_patient_a_notification(ref, monkeypatch):
    patient_a, _ = resolved_by_reception(ref, monkeypatch)
    notifications.run_once()
    item = patient_a.get("/api/me/notifications").json()["notifications"][0]
    register_patient("Demo Patient B", "9000000012", patient_id=B)
    b = TestClient(create_app(session_service=InMemorySessionService()))
    code = b.post("/api/login/start", json={"patient_id": B, "phone": "9000000012"}).json()["demo_code"]
    b.post("/api/login/verify", json={"patient_id": B, "code": code})
    assert b.get("/api/me/notifications").json()["notifications"] == []
    unknown = b.post("/api/me/notifications/NTF-00000000/read")
    other = b.post(f"/api/me/notifications/{item['id']}/read")
    assert other.status_code == unknown.status_code == 404 and other.json() == unknown.json()
    opened = b.get(f"/api/me/appointments/{ref}")                          # link ka record
    assert opened.status_code == 404 and FRIDAY not in opened.text
    assert patient_a.get(f"/api/me/notifications/{item['id']}").status_code in (404, 405)   # koi detail route nahin
    assert TestClient(create_app(session_service=InMemorySessionService())).get(
        "/api/me/notifications").status_code == 401                        # bina login kuch nahin


def test_6_reminder_for_a_cancelled_appointment_is_skipped(ref):
    pending = request_booking("cardiology", FRIDAY, "11:00", make_ctx("book", patient=A))
    booked = confirm_pending(pending["action_id"], "patient_001", "s1", pending["fingerprint"], A)
    reminders = outbox("appointment.reminder")
    assert len(reminders) == 1 and reminders[0]["next_attempt_at"].startswith("2026-11-19T11:00")
    assert notifications.run_once() == []                                  # abhi samay nahin
    his.get_his().cancel(booked["appointment_id"], A)
    result = notifications.run_once(FIXED_NOW + timedelta(days=3, hours=4, minutes=1))
    assert result[0]["status"] == "skipped" and result[0]["reason"] == "appointment cancelled"
    assert inbox_count() == 0


def test_6b_reminder_for_a_live_appointment_is_delivered_and_old_time_is_dropped(ref, monkeypatch):
    resolved_by_reception(ref, monkeypatch)                                # Monday 09:00 -> Friday 10:00
    notifications.run_once()
    thursday = FIXED_NOW + timedelta(days=3, hours=3, minutes=1)
    assert [r["status"] for r in notifications.run_once(thursday)] == ["delivered"]
    kinds = [n["event_type"] for n in notifications.inbox(A)["notifications"]]
    assert sorted(kinds) == ["appointment.reminder", "appointment.rescheduled"]


def test_reminder_for_an_appointment_that_moved_is_skipped(ref):
    pending = request_booking("cardiology", FRIDAY, "11:00", make_ctx("book", patient=A))
    booked = confirm_pending(pending["action_id"], "patient_001", "s1", pending["fingerprint"], A)
    with db.connect() as conn:                                             # staff ne seedha HIS me badla
        db.staff_move(conn, booked["appointment_id"], slot(FRIDAY, "12:00"), FRIDAY, "12:00")
    result = notifications.run_once(FIXED_NOW + timedelta(days=3, hours=4, minutes=1))
    assert result[0]["reason"] == "appointment moved" and inbox_count() == 0


def test_transient_failure_is_retried_later(ref, monkeypatch):
    resolved_by_reception(ref, monkeypatch)
    calls = []

    def flaky(event):
        calls.append(event["event_id"])
        if len(calls) == 1:
            raise OSError("database is locked")
        return notifications.deliver_in_app(event)

    monkeypatch.setattr(notifications, "CHANNELS", [flaky])
    assert notifications.run_once()[0]["status"] == "retry"
    assert notifications.run_once() == [] and inbox_count() == 0           # turant nahin; thoda ruk kar
    assert notifications.run_once(FIXED_NOW + timedelta(seconds=31))[0]["status"] == "delivered"
    assert inbox_count() == 1 and outbox("appointment.rescheduled")[0]["attempts"] == 2


def test_patient_own_reschedule_that_fails_sends_nothing(ref):
    client = patient_client()
    card = client.post(f"/api/me/appointments/{ref}/reschedule-preview", json={"slot_id": slot(FRIDAY, "10:00")}).json()
    register_patient("Demo Patient B", "9000000012", patient_id=B)
    his.get_his().book("OTHER", slot(FRIDAY, "10:00"), B)
    result = client.post(f"/api/me/reschedule-actions/{card['action_id']}/confirm",
                         json={"fingerprint": card["fingerprint"]}).json()["result"]
    assert result["original_kept"] and outbox("appointment.rescheduled") == []


def test_decline_sends_helpdesk_update_that_opens_the_request(ref, monkeypatch):
    patient = patient_client()
    item_id = handover(patient, ref, monkeypatch)
    staff = staff_client()
    staff.post(f"/api/staff/queue/{item_id}/claim")
    staff.post(f"/api/staff/queue/{item_id}/resolve", json={"decision": "decline", "note": "Doctor Friday ko nahin."})
    notifications.run_once()
    item = patient.get("/api/me/notifications").json()["notifications"][0]
    assert item["event_type"] == "reception.request_resolved" and item["destination"] == {"view": "request",
                                                                                         "id": item_id}
    request = patient.get(f"/api/me/requests/{item_id}").json()
    assert request["status"] == "resolved" and "Doctor Friday" in request["message"]


def test_lab_report_release_notifies_once(ref):
    with db.connect() as conn:
        db.save_lab_test(conn, {"id": "LAB-A-009", "patient_ref": A, "visit_ref": "V1", "test_name": "CBC",
                                "department_id": "general_medicine", "ordered_on": MONDAY, "status": "processing",
                                "report_released": 0, "report_pdf": None})
    assert records.release_lab_report("LAB-A-009", b"%PDF-1.4 synthetic") is True
    assert records.release_lab_report("LAB-A-009", b"%PDF-1.4 again") is False   # dobara release: naya event nahin
    notifications.run_once()
    items = notifications.inbox(A)["notifications"]
    assert [(i["event_type"], i["destination"]["id"]) for i in items] == [("lab.report_released", "LAB-A-009")]
    assert "CBC" not in str(items)                                         # test ka naam bhi nahin; sirf dashboard me


def test_chat_tool_reports_the_confirmed_status(ref, monkeypatch):
    from hospital_agent.tools.updates import my_updates
    _, item_id = resolved_by_reception(ref, monkeypatch)
    notifications.run_once()
    status = my_updates(make_ctx("meri request ka kya hua?", patient=A))
    assert status["requests"][0]["status"] == "Resolved" and "badal di" in status["requests"][0]["message"]
    assert status["notifications"][0]["title"] == "Appointment updated"
    assert my_updates(make_ctx("update?"))["status"] == "login_required"
