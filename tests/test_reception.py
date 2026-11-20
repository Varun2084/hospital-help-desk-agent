"""Reception work queue: staff ka alag login, claim (ek hi staff), aur hal (laagu / mana / scheduler se jaanch).

Kaam do jagah se aate hain:
  - reschedule jo scheduler khud nahin le saka (Lesson 6 ka handover)
  - booking ya reschedule jiska nateeja saaf nahin ('committing') aur expiry ke baad bhi wahi
"""

from datetime import timedelta

import pytest
from conftest import FIXED_NOW, register_patient
from fastapi.testclient import TestClient
from google.adk.sessions import InMemorySessionService

from hospital_agent import db, his
from hospital_agent.his import slots
from hospital_agent.tools import common
from web_app import create_app

A = "DEMO-PATIENT-A"
PHONE_A = "9000000011"
STAFF = {"STAFF-RECEPTION-1": "9000000021", "STAFF-RECEPTION-2": "9000000022"}
MONDAY, FRIDAY = "2026-11-16", "2026-11-20"


def slot(date, time):
    return slots.make_slot_id("cardiology", date, time)


@pytest.fixture
def ref():
    register_patient("Demo Patient A", PHONE_A, patient_id=A)
    with db.connect() as conn:
        for sid, phone in STAFF.items():
            db.save_staff(conn, sid, f"Demo {sid[-1]}", phone)
    return his.get_his().book("SEED-A", slot(MONDAY, "09:00"), A).reference


def app():
    return create_app(session_service=InMemorySessionService())


def patient_client():
    c = TestClient(app())
    code = c.post("/api/login/start", json={"patient_id": A, "phone": PHONE_A}).json()["demo_code"]
    c.post("/api/login/verify", json={"patient_id": A, "code": code})
    return c


def staff_client(staff_id="STAFF-RECEPTION-1"):
    c = TestClient(app())
    code = c.post("/api/staff/login/start", json={"staff_id": staff_id, "phone": STAFF[staff_id]}).json()["demo_code"]
    assert c.post("/api/staff/login/verify", json={"staff_id": staff_id, "code": code}).status_code == 200
    return c


def handover(patient, ref, monkeypatch):
    """Patient ne reschedule maanga; scheduler me API nahin, to kaam reception ke paas."""
    card = patient.post(f"/api/me/appointments/{ref}/reschedule-preview",
                        json={"slot_id": slot(FRIDAY, "10:00")}).json()

    def unsupported(*args, **kwargs):
        raise his.RescheduleUnsupported(ref)

    real = his.LocalHIS.reschedule
    monkeypatch.setattr(his.LocalHIS, "reschedule", unsupported)
    result = patient.post(f"/api/me/reschedule-actions/{card['action_id']}/confirm",
                          json={"fingerprint": card["fingerprint"]}).json()["result"]
    monkeypatch.setattr(his.LocalHIS, "reschedule", real)   # ab scheduler fir se reschedule kar sakta hai
    assert result["status"] == "reception_review"
    return result["queue_id"]


def test_only_reception_staff_can_open_the_queue(ref):
    assert TestClient(app()).get("/api/staff/queue").status_code == 401
    patient = patient_client()
    assert patient.get("/api/staff/queue").status_code == 401              # patient cookie se staff ka kaam nahin
    patient.cookies.set("opd_staff", patient.cookies.get("opd_session"))   # patient token ko staff cookie me daala
    assert patient.get("/api/staff/queue").status_code == 401              # role 'patient' hai: phir bhi nahin
    staff = staff_client()
    assert staff.get("/api/staff/queue").status_code == 200
    assert staff.get("/api/me/appointments").status_code == 401            # staff session patient nahin
    wrong = TestClient(app()).post("/api/staff/login/start", json={"staff_id": A, "phone": PHONE_A})
    assert wrong.status_code == 400                                         # patient ID se staff login nahin


def test_reschedule_handover_claim_and_apply(ref, monkeypatch):
    patient = patient_client()
    item_id = handover(patient, ref, monkeypatch)
    one, two = staff_client("STAFF-RECEPTION-1"), staff_client("STAFF-RECEPTION-2")
    items = one.get("/api/staff/queue", params={"status": "pending"}).json()["items"]
    assert [i["id"] for i in items] == [item_id] and items[0]["current"]["time"] == "09:00"
    assert items[0]["patient"]["phone"] == PHONE_A                         # staff ko call ke liye number
    assert one.post(f"/api/staff/queue/{item_id}/claim").status_code == 200
    assert two.post(f"/api/staff/queue/{item_id}/claim").status_code == 409   # ek hi staff
    assert two.post(f"/api/staff/queue/{item_id}/resolve", json={"decision": "apply"}).json()["status"] == "error"
    done = one.post(f"/api/staff/queue/{item_id}/resolve", json={"decision": "apply"}).json()
    assert done["resolution"] == "changed" and (done["booking"]["date"], done["booking"]["time"]) == (FRIDAY, "10:00")
    mine = patient.get("/api/me/requests").json()["requests"][0]
    assert mine["status"] == "resolved" and "badal di" in mine["message"] and "STAFF" not in str(mine)


def test_decline_needs_a_reason_and_keeps_the_booking(ref, monkeypatch):
    patient = patient_client()
    item_id = handover(patient, ref, monkeypatch)
    staff = staff_client()
    staff.post(f"/api/staff/queue/{item_id}/claim")
    assert staff.post(f"/api/staff/queue/{item_id}/resolve", json={"decision": "decline"}).json()["status"] == "error"
    done = staff.post(f"/api/staff/queue/{item_id}/resolve",
                      json={"decision": "decline", "note": "Doctor Friday ko OPD me nahin hain."}).json()
    assert done["resolution"] == "declined"
    assert his.get_his().find_for_patient(A, ref).date == MONDAY
    assert "Doctor Friday" in patient.get("/api/me/requests").json()["requests"][0]["message"]


def test_apply_when_slot_is_gone_offers_alternatives(ref, monkeypatch):
    patient = patient_client()
    item_id = handover(patient, ref, monkeypatch)
    register_patient("Demo Patient B", "9000000012", patient_id="DEMO-PATIENT-B")
    his.get_his().book("B", slot(FRIDAY, "10:00"), "DEMO-PATIENT-B")      # beech me kisi aur ne le liya
    staff = staff_client()
    staff.post(f"/api/staff/queue/{item_id}/claim")
    result = staff.post(f"/api/staff/queue/{item_id}/resolve", json={"decision": "apply"}).json()
    assert result["status"] == "error" and result["alternatives"]
    assert his.get_his().find_for_patient(A, ref).date == MONDAY          # purani chalu, kaam abhi khula
    assert staff.get("/api/staff/queue", params={"status": "in_review"}).json()["items"][0]["id"] == item_id


def _stuck_booking(monkeypatch, reach_his: bool):
    """Patient ne Confirm dabaya, jawab nahin aaya, aur patient ne 'Check status' kabhi nahin dabaya."""
    patient = patient_client()
    from conftest import make_ctx

    from hospital_agent.tools.actions import confirm_pending
    from hospital_agent.tools.appointments import request_booking
    pending = request_booking("cardiology", MONDAY, "10:00", make_ctx("book", patient=A))
    real_book = his.LocalHIS.book

    def lost(self, *args):
        if reach_his:
            real_book(self, *args)          # scheduler me ban gayi...
        raise his.HISTimeout("lost")         # ...par jawab nahin aaya

    monkeypatch.setattr(his.LocalHIS, "book", lost)
    first = confirm_pending(pending["action_id"], "patient_001", "s1", pending["fingerprint"], A)
    assert first["status"] == "in_progress"
    monkeypatch.setattr(his.LocalHIS, "book", real_book)
    monkeypatch.setattr(common, "now", lambda: FIXED_NOW + timedelta(minutes=15))   # expiry ke baad
    return patient, pending


@pytest.mark.parametrize("reach_his, resolution, action_status", [
    (True, "verified_done", "done"), (False, "verified_not_done", "failed")])
def test_unclear_booking_is_verified_by_staff(ref, monkeypatch, reach_his, resolution, action_status):
    patient, pending = _stuck_booking(monkeypatch, reach_his)
    staff = staff_client()
    items = staff.get("/api/staff/queue", params={"status": "pending"}).json()["items"]
    item = next(i for i in items if i["kind"] == "verify_booking")
    assert item["action_id"] == pending["action_id"]
    assert len(staff.get("/api/staff/queue").json()["items"]) == len(items)   # list dobara kholne par naya kaam nahin
    staff.post(f"/api/staff/queue/{item['id']}/claim")
    assert staff.post(f"/api/staff/queue/{item['id']}/resolve", json={"decision": "apply"}).json()["status"] == "error"
    done = staff.post(f"/api/staff/queue/{item['id']}/resolve", json={"decision": "check"}).json()
    assert done["resolution"] == resolution
    with db.connect() as conn:
        assert db.get_pending(conn, pending["action_id"])["status"] == action_status
        assert conn.execute("SELECT COUNT(*) FROM reception_queue WHERE action_id = ?",
                            (pending["action_id"],)).fetchone()[0] == 1          # ek arzi, ek kaam
    assert patient.get("/api/me/requests").json()["requests"][0]["resolution"] == resolution


def test_repeat_request_for_same_appointment_reuses_the_open_case(ref, monkeypatch):
    patient = patient_client()
    first = handover(patient, ref, monkeypatch)
    card = patient.post(f"/api/me/appointments/{ref}/reschedule-preview",
                        json={"slot_id": slot(FRIDAY, "11:00")}).json()

    def unsupported(*args, **kwargs):
        raise his.RescheduleUnsupported(ref)

    monkeypatch.setattr(his.LocalHIS, "reschedule", unsupported)
    again = patient.post(f"/api/me/reschedule-actions/{card['action_id']}/confirm",
                         json={"fingerprint": card["fingerprint"]}).json()["result"]
    assert again["status"] == "reception_review" and again["queue_id"] == first
    items = staff_client().get("/api/staff/queue", params={"status": "pending"}).json()["items"]
    assert len(items) == 1 and items[0]["details"]["requested_slot_id"] == slot(FRIDAY, "11:00")
    assert items[0]["details"]["earlier_requests"] == [f"{FRIDAY} 10:00"]
