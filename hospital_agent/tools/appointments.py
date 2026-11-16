"""Appointment tools: khaali slot dekhna, booking ya cancel ki arzi, aur Confirm button ke baad use poora karna.

Arzi yahan banti hai; use patient ka Confirm button (tools/actions.py) pakka karta hai.
Slot aur booking HIS (hospital ka system) ke paas hain: yeh file sirf hospital_agent.his ke contract se baat karti hai.
Booking sirf registered patient ki hoti hai (patient_ref = DEMO patient ID).
"""

import re
from datetime import date as Date
from datetime import datetime, timedelta
from datetime import time as Time

from google.adk.tools import ToolContext

from hospital_agent import db, his
from hospital_agent.config import feature_required, get_department
from hospital_agent.safety import mask_phone
from hospital_agent.tools import common
from hospital_agent.tools.common import IST, PHONE_PATTERN, create_pending_action, error

BOOKING_WINDOW_DAYS = 30
HIS_DOWN = "Hospital ka system abhi jawab nahin de raha. Thodi der baad koshish karein ya reception se baat karein."
IN_PROGRESS = ("Hospital ke system se jawab samay par nahin aaya. Booking ki sthiti jaanchi ja rahi hai: "
               "'Status jaanchein' dabayein. Isse doosri booking nahin banegi; HIS me bani ho to wahi milegi.")
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


@feature_required("appointments")
def today_date() -> dict:
    """Returns today's date and weekday. Call this before working out dates like 'tomorrow' or 'next Monday'.

    Returns:
        Today's date in YYYY-MM-DD format and the weekday.
    """
    day = common.today()
    return {"today": day.isoformat(), "weekday": day.strftime("%A")}


def parse_booking_date(value: str) -> Date:
    """Sirf YYYY-MM-DD chalega. '20261116' jaisa likhne par ValueError."""
    if not DATE_PATTERN.fullmatch(value.strip()):
        raise ValueError("Expected YYYY-MM-DD")
    return Date.fromisoformat(value.strip())


def is_future_slot(day: Date, hhmm: str, moment: datetime) -> bool:
    """Kya yeh slot 'moment' ke baad shuru hota hai?"""
    return datetime.combine(day, Time.fromisoformat(hhmm), tzinfo=IST) > moment


def _check_department_and_date(department_id: str, date: str, moment: datetime):
    """Department aur tareekh ki jaanch. Sahi ho to (dept, day, None), galat ho to (None, None, error)."""
    dept = get_department(department_id)
    if dept is None or not dept.active:
        return None, None, error(f"'{department_id}' me abhi OPD booking nahin ho sakti.")
    try:
        day = parse_booking_date(date)
    except ValueError:
        return None, None, error("Tareekh YYYY-MM-DD format me dein, jaise 2026-11-20.")
    if day < moment.date():
        return None, None, error("Beeti hui tareekh par booking nahin ho sakti.")
    if day > moment.date() + timedelta(days=BOOKING_WINDOW_DAYS):
        return None, None, error(f"Booking sirf agle {BOOKING_WINDOW_DAYS} din tak ki ho sakti hai.")
    weekday = day.strftime("%a")
    if weekday not in dept.opd_days:
        return None, None, error(
            f"{dept.name} ki OPD {weekday} ko nahin hoti. OPD ke din: {', '.join(dept.opd_days)}."
        )
    return dept, day, None


def _open_slots(dept, day: Date, moment: datetime) -> list[his.Slot]:
    """HIS se khaali slot, aur unme se sirf woh jo abhi ke baad shuru hote hain."""
    return [slot for slot in his.get_his().open_slots(dept.id, day.isoformat())   # HISError upar jaata hai
            if is_future_slot(day, slot.time, moment)]


def _fresh_times(department_id: str, date: str, moment: datetime, limit: int = 6) -> list[str]:
    """Slot chhin jaane par card ke liye naye khaali samay. HIS na chale to khaali list."""
    dept = get_department(department_id)
    try:
        return [s.time for s in _open_slots(dept, Date.fromisoformat(date), moment)][:limit] if dept else []
    except his.HISError:
        return []


@feature_required("appointments")
def check_available_slots(department_id: str, date: str) -> dict:
    """Shows free appointment times for a department on a date, from the hospital scheduler. Read-only.

    Args:
        department_id: The department's id, for example 'cardiology'.
        date: The date in YYYY-MM-DD format.

    Returns:
        The list of free times, or an error explaining why booking is not possible.
    """
    moment = common.now()  # poori request me ek hi 'abhi'
    dept, day, problem = _check_department_and_date(department_id, date, moment)
    if problem:
        return problem
    try:
        free = [s.time for s in _open_slots(dept, day, moment)]
    except his.HISError:
        return error(HIS_DOWN)
    return {"status": "ok", "department": dept.name, "date": day.isoformat(), "free_slots": free}


@feature_required("appointments")
def request_booking(patient_name: str, phone: str, department_id: str, date: str, time: str,
                    tool_context: ToolContext) -> dict:
    """Prepares an OPD booking for a REGISTERED patient and returns a summary.
    Nothing is booked yet: the patient confirms it with a button in the app.
    If the patient is not registered, it returns 'not_registered': registration comes first.

    Args:
        patient_name: The patient's full name, as registered.
        phone: The 10-digit Indian mobile number given at registration.
        department_id: The department's id, for example 'cardiology'.
        date: The date in YYYY-MM-DD format.
        time: A free slot time from check_available_slots, for example '09:30'.

    Returns:
        An action_id and the exact summary to confirm, 'not_registered', or an error.
    """
    moment = common.now()
    name = " ".join(patient_name.split())
    if not name:
        return error("Patient ka naam chahiye.")
    if not PHONE_PATTERN.fullmatch(phone):
        return error("Phone 10 ankon ka Indian mobile number hona chahiye (6, 7, 8 ya 9 se shuru).")
    with db.connect() as conn:
        patient = db.find_patient(conn, phone, name)
    if patient is None:
        return {"status": "not_registered",
                "message": "Is naam aur phone se registration nahin mila. Appointment se pehle registration "
                           "zaroori hai: registration desk naam, umar, gender, phone aur shahar lekar patient ID "
                           "dega. Registration ho chuka ho to wahi naam aur phone dein jo registration me diye the."}
    dept, day, problem = _check_department_and_date(department_id, date, moment)
    if problem:
        return problem
    try:
        slot = next((s for s in _open_slots(dept, day, moment) if s.time == time), None)
    except his.HISError:
        return error(HIS_DOWN)
    if slot is None:
        return error(f"{time} ka slot khaali nahin hai (beet chuka, booked, ya schedule me nahin). "
                     "check_available_slots se khaali samay dekhein.")
    payload = {"slot_id": slot.slot_id, "patient_ref": patient["id"], "department_id": dept.id,
               "date": day.isoformat(), "time": time}
    summary = {"action": "book", "patient_id": patient["id"], "patient_name": patient["full_name"],
               "phone": mask_phone(phone), "department": dept.name,
               "location": f"{dept.building}, floor {dept.floor}", "date": day.isoformat(),
               "weekday": day.strftime("%A"), "time": time}
    return create_pending_action("book", payload, summary, tool_context)


@feature_required("appointments")
def request_cancellation(appointment_id: str, phone: str, tool_context: ToolContext) -> dict:
    """Prepares the cancellation of an appointment and returns a summary to read back.
    Nothing is cancelled yet: the patient confirms it with a button in the app.

    Args:
        appointment_id: The booking reference given at booking, for example 'HIS-APT-001' or 'APT-1A2B3C'.
        phone: The 10-digit mobile number of the registered patient.

    Returns:
        An action_id and the exact summary to confirm, or an error.
    """
    apt_id = appointment_id.strip().upper()
    try:
        booking = his.get_his().get_booking(apt_id)
    except his.HISError:
        return error(HIS_DOWN)
    with db.connect() as conn:
        patient = db.get_patient(conn, booking.patient_ref) if booking else None
    if booking is None or patient is None or patient["phone"] != phone:
        return error("Is ID aur phone number se koi appointment nahin mili.")
    if booking.status != "confirmed":
        return error("Yeh appointment pehle hi cancel ho chuki hai.")
    payload = {"appointment_id": apt_id, "patient_ref": booking.patient_ref}
    summary = {"action": "cancel", "appointment_id": apt_id, "patient_id": booking.patient_ref,
               "date": booking.date, "time": booking.time}
    return create_pending_action("cancel", payload, summary, tool_context)


def _booked_outcome(booking: his.Booking, recovered: bool = False) -> dict:
    dept = get_department(booking.department_id)
    with db.connect() as conn:
        patient = db.get_patient(conn, booking.patient_ref)
    outcome = {
        "status": "booked",
        "appointment_id": booking.reference,
        "patient_id": booking.patient_ref,
        "patient_name": patient["full_name"] if patient else "",
        "phone": mask_phone(patient["phone"]) if patient else "",
        "department": dept.name if dept else booking.department_id,
        "location": f"{dept.building}, floor {dept.floor}" if dept else "",
        "date": booking.date,
        "time": booking.time,
        "reminder": "Registration card aur photo ID ke saath 30 minute pehle pahunchein.",
    }
    if recovered:
        outcome["note"] = "Pichhli koshish me jawab nahin aaya tha; HIS me wahi booking mili, nayi nahin bani."
    return outcome


def complete_booking(conn, action_id: str, p: dict, moment: datetime) -> dict:
    """Confirm button (actions.confirm_pending) ise bulata hai. Arzi ki id hi HIS ki request_id hai:
    timeout ke baad dobara dabane par HIS se usi request_id ki booking poochhi jaati hai, doosri nahin banti."""
    if "slot_id" not in p:   # v0.9 se pehle bani arzi
        outcome = error("Yeh purani request hai. Kripya slot dobara chunein.")
        db.fail_pending(conn, action_id, outcome)
        return outcome
    system = his.get_his()
    if db.get_pending(conn, action_id)["status"] == "committing":   # pichhli baar jawab nahin aaya tha
        try:
            existing = system.find_by_request(action_id)
        except his.HISError:
            return {"status": "in_progress", "action_id": action_id, "message": IN_PROGRESS}
        if existing is not None:
            outcome = _booked_outcome(existing, recovered=True)
            db.finish_pending(conn, action_id, outcome)
            return outcome
        # HIS me is request_id ki booking nahin bani: wahi request_id ke saath dobara bhejna surakshit hai

    dept = get_department(p["department_id"])
    day = Date.fromisoformat(p["date"])
    if dept is None or not dept.active or not is_future_slot(day, p["time"], moment):
        outcome = error("Yeh slot ab uplabdh nahin hai. Doosra samay chunein.")
        outcome["free_slots"] = _fresh_times(p["department_id"], p["date"], moment)
        db.fail_pending(conn, action_id, outcome)
        return outcome

    db.mark_committing(conn, action_id)   # HIS ko bhejne se PEHLE: request_id save
    try:
        booking = system.book(action_id, p["slot_id"], p["patient_ref"])
    except his.SlotTaken:
        outcome = error(f"{p['time']} ka slot abhi-abhi kisi aur ne le liya. Neeche se naya samay chunein.")
        outcome.update(free_slots=_fresh_times(p["department_id"], p["date"], moment),
                       department_id=p["department_id"], date=p["date"])
        db.fail_pending(conn, action_id, outcome)
        return outcome
    except (his.HISTimeout, his.HISUnavailable):
        return {"status": "in_progress", "action_id": action_id, "message": IN_PROGRESS}
    except his.HISError:
        outcome = error(HIS_DOWN)
        db.fail_pending(conn, action_id, outcome)
        return outcome
    outcome = _booked_outcome(booking)
    db.finish_pending(conn, action_id, outcome)
    return outcome


def complete_cancellation(conn, action_id: str, p: dict, moment: datetime) -> dict:
    """Confirm button (actions.confirm_pending) ise bulata hai. HIS me cancel; dobara bulane par bhi surakshit."""
    if "patient_ref" not in p:   # v0.9 se pehle bani arzi
        outcome = error("Yeh purani request hai. Kripya cancel dobara shuru karein.")
        db.fail_pending(conn, action_id, outcome)
        return outcome
    db.mark_committing(conn, action_id)
    try:
        booking = his.get_his().cancel(p["appointment_id"], p["patient_ref"])
    except his.BookingNotFound:
        outcome = error("Yeh appointment nahin mili; cancel nahin hui.")
        db.fail_pending(conn, action_id, outcome)
        return outcome
    except (his.HISTimeout, his.HISUnavailable):
        return {"status": "in_progress", "action_id": action_id, "message": IN_PROGRESS}
    except his.HISError:
        outcome = error(HIS_DOWN)
        db.fail_pending(conn, action_id, outcome)
        return outcome
    outcome = {"status": "cancelled", "appointment_id": booking.reference, "date": booking.date, "time": booking.time}
    db.finish_pending(conn, action_id, outcome)
    return outcome
