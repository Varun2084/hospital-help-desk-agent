"""Reception work queue: jo kaam system khud poora nahin kar saka, woh staff ke paas.

Do tarah ke kaam:
  reschedule       hospital ke scheduler me reschedule ka API nahin tha (Lesson 6 ka handover)
  verify_booking / verify_reschedule
                   arzi scheduler ko gayi, par nateeja saaf nahin ('committing') aur expiry ke baad bhi wahi.
                   Staff scheduler se usi request_id par poochhta hai, aur arzi ko pakka ya radd karta hai.

Kram: pending -> in_review (ek staff "claim" karta hai; doosra nahin le sakta) -> resolved.
Har kaam par kaun, kab, kya faisla, aur patient ko dashboard par kya sandesh: sab likha rehta hai.
"""

import json
from datetime import datetime

from hospital_agent import db, his, notifications, reschedule
from hospital_agent.tools import common
from hospital_agent.tools.appointments import _booked_outcome, appointment_view
from hospital_agent.tools.common import error

MESSAGES = {
    "changed": "Reception ne aapki appointment badal di hai.",
    "changed_manually": "Reception ne hospital system me aapki appointment badal di hai.",
    "declined": "Reception yeh badlaav nahin kar saka.",
    "verified_done": "Aapki request hospital system me pakki mili.",
    "verified_not_done": "Aapki request hospital system me nahin bani. Kripya dobara koshish karein.",
}


def sweep_unclear(moment: datetime | None = None) -> int:
    """Atki hui arziyan (committing, expiry ke baad) queue me. Har arzi ka ek hi kaam. Kitne naye bane."""
    moment = moment or common.now()
    added = 0
    with db.connect() as conn:
        for action in db.stuck_actions(conn, moment.isoformat(timespec="seconds")):
            p = json.loads(action["payload"])
            before = conn.execute("SELECT 1 FROM reception_queue WHERE action_id = ?", (action["id"],)).fetchone()
            if before:
                continue
            kind = "verify_booking" if action["kind"] == "book" else "verify_reschedule"
            details = {"requested": f"{p['date']} {p['time']}", "slot_id": p.get("slot_id") or p.get("new_slot_id"),
                       "action_id": action["id"]}
            db.add_to_reception_queue(conn, kind, p["patient_ref"], p.get("booking_ref", ""), details, action["id"])
            added += 1
    return added


def _view(row, conn) -> dict:
    patient = db.get_patient(conn, row["patient_ref"])
    item = {k: row[k] for k in ("id", "kind", "status", "booking_ref", "created_at", "claimed_by", "claimed_at",
                                "resolved_by", "resolved_at", "resolution", "patient_message", "action_id")}
    item["details"] = json.loads(row["details"])
    item["patient"] = {"id": row["patient_ref"], "name": patient["full_name"] if patient else "",
                       "phone": patient["phone"] if patient else ""}   # staff ko poora number chahiye (call ke liye)
    # Patient tak update pahuncha? (outbox ka event: pending / delivered / failed)
    events = [f"appointment.rescheduled:STAFF-{row['id']}", f"reception.request_resolved:{row['id']}"]
    if row["action_id"]:
        events.append(f"appointment.rescheduled:{row['action_id']}")
    item["patient_update"] = db.outbox_status(conn, events)
    return item


def queue(status: str | None = None) -> list[dict]:
    """Staff ki list. Pehle atki arziyan queue me laata hai, phir har kaam ke saath booking ki abhi ki haalat."""
    sweep_unclear()
    with db.connect() as conn:
        items = [_view(row, conn) for row in db.reception_queue(conn, status)]
    for item in items:
        if item["booking_ref"]:
            try:
                booking = his.get_his().find_for_patient(item["patient"]["id"], item["booking_ref"])
                item["current"] = appointment_view(booking) if booking else None
            except his.HISError:
                item["current"] = None
    return items


def claim(item_id: str, staff_id: str) -> dict:
    with db.connect() as conn:
        if not db.claim_queue_item(conn, item_id, staff_id):
            row = db.get_queue_item(conn, item_id)
            who = row["claimed_by"] if row else None
            return error(f"Yeh kaam pehle se {who} ke paas hai." if who else "Yeh kaam nahin mila ya band ho chuka.")
        return {"status": "ok", "item": _view(db.get_queue_item(conn, item_id), conn)}


def resolve(item_id: str, staff_id: str, decision: str, note: str = "") -> dict:
    """decision: reschedule ke liye 'apply' / 'done_manually' / 'decline'; verify ke liye 'check'."""
    with db.connect() as conn:
        row = db.get_queue_item(conn, item_id)
        if row is None or row["status"] != "in_review" or row["claimed_by"] != staff_id:
            return error("Pehle yeh kaam claim karein (sirf claim karne wala staff ise band kar sakta hai).")
        details = json.loads(row["details"])
    note = " ".join(note.split())[:300]
    if row["kind"] == "reschedule":
        return _resolve_reschedule(row, details, staff_id, decision, note)
    if decision != "check":
        return error("Is kaam ke liye 'check' chunein: scheduler se nateeja poochha jaayega.")
    return _resolve_verify(row, staff_id)


def _close(item_id: str, staff_id: str, resolution: str, note: str = "", extra: dict | None = None,
           events: list[dict] | None = None) -> dict:
    """Kaam band. Patient ki notification ka event isi transaction me (default: 'helpdesk request par update')."""
    message = MESSAGES[resolution] + (f" {note}" if note else "")
    with db.connect() as conn:
        patient_ref = db.get_queue_item(conn, item_id)["patient_ref"]
        if events is None:
            events = notifications.request_resolved(item_id, patient_ref, resolution)
        db.resolve_queue_item(conn, item_id, staff_id, resolution, message, events)
        item = _view(db.get_queue_item(conn, item_id), conn)
    return {"status": "resolved", "resolution": resolution, "item": item, **(extra or {})}


def _resolve_reschedule(row, details: dict, staff_id: str, decision: str, note: str) -> dict:
    if decision == "decline":
        if not note:
            return error("Mana karne ki wajah likhein; yeh patient ko dikhegi.")
        return _close(row["id"], staff_id, "declined", note)
    if decision == "done_manually":
        return _close(row["id"], staff_id, "changed_manually", note)
    if decision != "apply":
        return error("decision: apply, done_manually ya decline.")
    system = his.get_his()   # staff ki taraf se scheduler ko; request_id staff ke kaam se bandhi (retry surakshit)
    try:
        booking = system.find_for_patient(row["patient_ref"], row["booking_ref"])
        if booking is None:
            return error("Booking scheduler me nahin mili.")
        moved = system.reschedule(f"STAFF-{row['id']}", row["booking_ref"], row["patient_ref"], booking.version,
                                  details["requested_slot_id"])
    except his.SlotTaken:
        options = reschedule.options_for(booking, common.now())
        return {**error("Maanga gaya slot ab khaali nahin. Patient se baat karke doosra slot dein, ya mana karein."),
                "alternatives": options if isinstance(options, list) else []}
    except his.RescheduleUnsupported:
        return error("Scheduler me reschedule ka API nahin. Hospital system me khud badlein, phir 'done_manually'.")
    except his.StaleBooking as e:
        return {**error("Booking beech me badal chuki hai; abhi ki haalat dekhein."),
                "current": appointment_view(e.booking)}
    except his.HISError:
        return error("Hospital system abhi jawab nahin de raha.")
    # Scheduler ne confirm kiya: patient ko "appointment updated" (helpdesk wali alag notification nahin)
    return _close(row["id"], staff_id, "changed", f"Naya samay: {moved.date} {moved.time}.",
                  {"booking": appointment_view(moved)}, events=notifications.rescheduled(f"STAFF-{row['id']}", moved))


def _resolve_verify(row, staff_id: str) -> dict:
    """Usi request_id se scheduler se poochho; arzi ko pakka ya radd karo, taaki patient ko saaf jawab mile."""
    system = his.get_his()
    action_id = row["action_id"]
    try:
        if row["kind"] == "verify_booking":
            found = system.find_by_request(action_id)
        else:
            found = system.find_reschedule_by_request(action_id)
    except his.HISError:
        return error("Hospital system abhi jawab nahin de raha. Baad me 'check' karein.")
    with db.connect() as conn:
        p = json.loads(db.get_pending(conn, action_id)["payload"])
        if found is not None:
            if row["kind"] == "verify_booking":
                outcome, events = _booked_outcome(found, recovered=True), notifications.booked(found)
            else:
                outcome = reschedule._changed(found, p, recovered=True)
                events = notifications.rescheduled(action_id, found)
            db.finish_pending(conn, action_id, outcome, events)
        else:
            outcome = error("Hospital system me yeh request nahin bani. Kripya dobara koshish karein.")
            db.fail_pending(conn, action_id, outcome)
    resolution = "verified_done" if found is not None else "verified_not_done"
    # Badlaav pakka mila to "appointment updated" upar ban chuka; baaki sab me "helpdesk request par update"
    only_changed = found is not None and row["kind"] == "verify_reschedule"
    return _close(row["id"], staff_id, resolution, extra={"outcome": outcome}, events=[] if only_changed else None)


def requests_for_patient(patient_ref: str) -> list[dict]:
    """Patient ko apni requests ki sthiti (staff ka naam ya phone nahin)."""
    with db.connect() as conn:
        rows = db.queue_items_for_patient(conn, patient_ref)
    return [{"id": r["id"], "kind": r["kind"], "booking_ref": r["booking_ref"], "status": r["status"],
             "requested": json.loads(r["details"]).get("requested"), "resolution": r["resolution"],
             "message": r["patient_message"], "created_at": r["created_at"]} for r in rows]
