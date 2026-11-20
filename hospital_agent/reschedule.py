"""Lesson 6: appointment reschedule. Chat aur dashboard dono yahi ek workflow bulate hain.

    1. alternatives()    login kiye patient ki apni aane wali appointment ke liye scheduler se khaali slot
    2. create_preview()  chuna slot jaancho, arzi banao: patient_ref, booking_ref, booking ka version,
                         new_slot_id aur expiry. Card: Current appointment vs New appointment.
    3. complete_reschedule()  Confirm change par (actions.confirm_pending se): scheduler ko ek transaction.
       Naya slot na mile to purani booking chalu aur naye vikalp; preview ke baad booking badli ho to
       purana preview radd; timeout par request_id se nateeja; scheduler me API na ho to reception ko.

AI patient ki pasand samajhta hai ("Friday afternoon"); vikalp scheduler deta hai; badlaav patient ka button karta hai.
"""


from datetime import date as Date
from datetime import datetime, timedelta

from hospital_agent import db, his, notifications
from hospital_agent.config import get_department
from hospital_agent.his import slots as roster
from hospital_agent.tools import common
from hospital_agent.tools.appointments import (
    BOOKING_WINDOW_DAYS,
    HIS_DOWN,
    _check_department_and_date,
    appointment_view,
    is_future_slot,
)
from hospital_agent.tools.common import error

PARTS = {"morning": (0, 12 * 60), "afternoon": (12 * 60, 17 * 60), "evening": (17 * 60, 24 * 60),
         "any": (0, 24 * 60)}
MAX_OPTIONS = 12          # ek din ke liye
MAX_DAYS, PER_DAY = 6, 6  # bina tareekh: aage ke 6 OPD din, har din ke 6 vikalp
NOT_FOUND = "Aapke account me is ID ki koi aane wali appointment nahin mili."
CHANGE_PENDING = ("Hospital ke system se jawab samay par nahin aaya. Badlaav ki sthiti jaanchi ja rahi hai: "
                  "'Status jaanchein' dabayein. Doosra badlaav nahin banega; purani ya nayi, ek hi appointment rahegi.")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _upcoming_own(patient_ref: str, booking_ref: str, moment: datetime):
    """Sirf apni, pakki aur aane wali appointment. Doosre ki ya beeti hui: None (ek hi jawab)."""
    booking = his.get_his().find_for_patient(patient_ref, booking_ref.strip().upper())
    if booking is None or booking.status != "confirmed":
        return None
    if not is_future_slot(Date.fromisoformat(booking.date), booking.time, moment):
        return None
    return booking


def _option(dept, day: Date, slot) -> dict:
    return {"slot_id": slot.slot_id, "date": day.isoformat(), "weekday": day.strftime("%A"), "time": slot.time,
            "location": f"{dept.building}, floor {dept.floor}"}


def options_for(booking, moment: datetime, date: str = "", part: str = "any") -> list[dict] | dict:
    """Scheduler se khaali slot: diya din, ya aage ke OPD din. Pasand (subah/dopahar/shaam) ke hisaab se."""
    dept = get_department(booking.department_id)
    low, high = PARTS.get((part or "any").strip().lower(), PARTS["any"])
    if date:
        days = [date]
    else:   # aage ke 14 din me OPD wale din
        days = [(moment.date() + timedelta(days=i)).isoformat() for i in range(0, 15)]
    found, day_count = [], 0
    for value in days:
        dept_ok, day, problem = _check_department_and_date(booking.department_id, value, moment)
        if problem:
            if date:
                return problem
            continue
        today_found = [_option(dept, day, slot) for slot in his.get_his().open_slots(dept_ok.id, day.isoformat())
                       if slot.slot_id != booking.slot_id and is_future_slot(day, slot.time, moment)
                       and low <= _minutes(slot.time) < high]
        if date:
            return today_found[:MAX_OPTIONS]
        if today_found:
            found += today_found[:PER_DAY]
            day_count += 1
        if day_count >= MAX_DAYS:
            break
    return found


def alternatives(patient_ref: str, booking_ref: str, date: str = "", part: str = "any") -> dict:
    moment = common.now()
    try:
        booking = _upcoming_own(patient_ref, booking_ref, moment)
        if booking is None:
            return error(NOT_FOUND)
        found = options_for(booking, moment, date, part)
    except his.HISError:
        return error(HIS_DOWN)
    if isinstance(found, dict):   # tareekh galat (format, beeti, OPD band)
        return found
    return {"status": "ok", "current": appointment_view(booking), "alternatives": found,
            "note": "No slot matches. Offer another day or part of day." if not found else ""}


def create_preview(patient_ref: str, booking_ref: str, new_slot_id: str, user_id: str, session_id: str,
                   invocation_id: str) -> dict:
    """Chuna slot dobara jaancho aur arzi banao. Appointment abhi nahin badalti."""
    moment = common.now()
    parsed = roster.parse_slot_id(new_slot_id or "")
    try:
        booking = _upcoming_own(patient_ref, booking_ref, moment)
        if booking is None:
            return error(NOT_FOUND)
        if parsed is None or parsed[0] != booking.department_id:
            return error("Yeh slot is appointment ke department ka nahin hai.")
        dept_id, date, time = parsed
        free = {s.slot_id for s in his.get_his().open_slots(dept_id, date)}
    except his.HISError:
        return error(HIS_DOWN)
    day = Date.fromisoformat(date)
    if day > moment.date() + timedelta(days=BOOKING_WINDOW_DAYS):
        return error(f"Sirf agle {BOOKING_WINDOW_DAYS} din tak.")
    if new_slot_id not in free or not is_future_slot(day, time, moment):
        return error(f"{time} ka slot ab khaali nahin hai. Doosra samay chunein.")
    dept = get_department(dept_id)
    payload = {"booking_ref": booking.reference, "patient_ref": patient_ref, "version": booking.version,
               "new_slot_id": new_slot_id, "department_id": dept_id, "date": date, "time": time,
               "current_date": booking.date, "current_time": booking.time}
    summary = {"action": "reschedule", "appointment_id": booking.reference, "department": dept.name,
               "location": f"{dept.building}, floor {dept.floor}",
               "current_date": booking.date, "current_time": booking.time,
               "new_date": date, "new_weekday": day.strftime("%A"), "new_time": time}
    result = common.create_pending_for("reschedule", payload, summary, user_id, session_id, invocation_id)
    result["next_step"] = ("The app shows the current and the new appointment with two buttons: 'Confirm change' "
                           "and 'Keep current appointment'. Nothing changes until the patient presses Confirm "
                           "change. You cannot confirm it yourself.")
    return result


def _fresh(p: dict, moment: datetime, booking=None) -> list[dict]:
    """Naya slot chhin gaya: usi din (ya aage) ke naye vikalp."""
    try:
        booking = booking or his.get_his().find_for_patient(p["patient_ref"], p["booking_ref"])
        found = options_for(booking, moment, p["date"]) if booking else []
        if isinstance(found, dict) or not found:
            found = options_for(booking, moment) if booking else []
        return found if isinstance(found, list) else []
    except his.HISError:
        return []


def _changed(booking, p: dict, recovered: bool = False) -> dict:
    view = appointment_view(booking)
    outcome = {"status": "rescheduled", "appointment_id": booking.reference, "department": view["department"],
               "location": view["location"], "date": booking.date, "weekday": view["weekday"],
               "time": booking.time, "previous_date": p.get("current_date"), "previous_time": p.get("current_time")}
    if recovered:
        outcome["note"] = "Pichhli koshish me jawab nahin aaya tha; scheduler me wahi badlaav mila, doosra nahin hua."
    return outcome


def complete_reschedule(conn, action_id: str, p: dict, moment: datetime) -> dict:
    """Confirm change button (actions.confirm_pending) ise bulata hai. Arzi ki id hi scheduler ki request_id."""
    system = his.get_his()
    if db.get_pending(conn, action_id)["status"] == "committing":   # pichhli baar jawab nahin aaya tha
        try:
            existing = system.find_reschedule_by_request(action_id)
        except his.HISError:
            return {"status": "in_progress", "action_id": action_id, "message": CHANGE_PENDING}
        if existing is not None:
            outcome = _changed(existing, p, recovered=True)
            db.finish_pending(conn, action_id, outcome, notifications.rescheduled(action_id, existing))
            return outcome

    if not is_future_slot(Date.fromisoformat(p["date"]), p["time"], moment):
        outcome = error("Naya samay beet chuka. Aapki purani appointment chalu hai; doosra samay chunein.")
        outcome.update(appointment_id=p["booking_ref"], alternatives=_fresh(p, moment))
        db.fail_pending(conn, action_id, outcome)
        return outcome

    db.mark_committing(conn, action_id)   # scheduler ko bhejne se PEHLE request_id save
    try:
        booking = system.reschedule(action_id, p["booking_ref"], p["patient_ref"], p["version"], p["new_slot_id"])
    except his.SlotTaken:
        outcome = error(f"{p['time']} ka slot abhi-abhi kisi aur ne le liya. Aapki purani appointment chalu hai. "
                        "Neeche se naya samay chunein.")
        outcome.update(appointment_id=p["booking_ref"], original_kept=True, alternatives=_fresh(p, moment))
        db.fail_pending(conn, action_id, outcome)
        return outcome
    except his.StaleBooking as e:
        outcome = error("Preview ke baad yeh appointment hospital me badal chuki hai. Neeche abhi ki appointment hai; "
                        "zaroorat ho to dobara reschedule karein.")
        outcome.update(appointment_id=p["booking_ref"], stale=True, current=appointment_view(e.booking))
        db.fail_pending(conn, action_id, outcome)
        return outcome
    except his.BookingNotFound:
        outcome = error(NOT_FOUND)
        db.fail_pending(conn, action_id, outcome)
        return outcome
    except his.RescheduleUnsupported:
        return _hand_over_to_reception(conn, action_id, p, moment)
    except (his.HISTimeout, his.HISUnavailable):
        return {"status": "in_progress", "action_id": action_id, "message": CHANGE_PENDING}
    except his.HISError:
        outcome = error(HIS_DOWN)
        db.fail_pending(conn, action_id, outcome)
        return outcome
    outcome = _changed(booking, p)
    # Pakka nateeja aur "appointment updated" ka event EK local transaction me (worker inbox tak le jaayega)
    db.finish_pending(conn, action_id, outcome, notifications.rescheduled(action_id, booking))
    return outcome


def _hand_over_to_reception(conn, action_id: str, p: dict, moment: datetime) -> dict:
    """Asli HIS me reschedule ka API nahin: staff ko poori jaankari, patient ko 'Reception review pending'."""
    details = {"requested_slot_id": p["new_slot_id"], "requested": f"{p['date']} {p['time']}",
               "alternatives": [o["slot_id"] for o in _fresh(p, moment)][:5], "action_id": action_id}
    already = db.open_queue_item(conn, "reschedule", p["patient_ref"], p["booking_ref"])
    if already:   # isi appointment ki request pehle se khuli: doosra case nahin, naya samay usi me
        db.update_queue_request(conn, already["id"], details)
        outcome = {"status": "reception_review", "appointment_id": p["booking_ref"], "queue_id": already["id"],
                   "message": "Is appointment ki request pehle se reception ke paas hai; naya pasandida samay usi "
                              "request me jod diya gaya hai. Tab tak aapki purani appointment chalu hai."}
        db.finish_pending(conn, action_id, outcome)
        return outcome
    item = db.add_to_reception_queue(conn, "reschedule", p["patient_ref"], p["booking_ref"], details, action_id)
    outcome = {"status": "reception_review", "appointment_id": p["booking_ref"], "queue_id": item,
               "message": "Hospital ka system yeh badlaav seedha nahin le sakta. Request reception ko bhej di gayi "
                          "hai; tab tak aapki purani appointment chalu hai."}
    db.finish_pending(conn, action_id, outcome)
    return outcome


def dashboard_owner(patient_ref: str) -> tuple[str, str, str]:
    """Dashboard se bani arzi ka maalik: login kiya patient (chat ki baat-cheet nahin)."""
    return f"dashboard:{patient_ref}", "dashboard", "dashboard"
