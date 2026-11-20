"""Appointment tools: khaali slot dekhna, booking ya cancel ki arzi, aur Confirm button ke baad use poora karna.

Arzi yahan banti hai; use patient ka Confirm button (tools/actions.py) pakka karta hai.
Slot aur booking HIS (hospital ka system) ke paas hain: yeh file sirf hospital_agent.his ke contract se baat karti hai.
Booking sirf login kiye hue patient ki hoti hai: patient_ref login session se aata hai, chat se nahin.
"""

import re
from datetime import date as Date
from datetime import datetime, timedelta
from datetime import time as Time

from google.adk.tools import ToolContext

from hospital_agent import db, his, notifications
from hospital_agent.config import feature_required, get_department
from hospital_agent.safety import mask_phone
from hospital_agent.tools import common
from hospital_agent.tools.common import IST, create_pending_action, error

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


LOGIN_NEEDED = ("Appointment patient ke apne account se hoti hai. Kripya upar 'Login' dabayein (Patient ID + "
                "registered phone). Chuna hua slot yaad rahega. Registration nahin hai to pehle registration karein.")


def _login_required(preview: dict | None = None) -> dict:
    result = {"status": "login_required", "message": LOGIN_NEEDED}
    if preview:
        result["preview"] = preview
    return result


@feature_required("appointments")
def request_booking(department_id: str, date: str, time: str, tool_context: ToolContext) -> dict:
    """Prepares an OPD booking for the LOGGED-IN patient and returns a summary.
    The patient is taken from the login, never from the chat: do not ask for name or phone.
    Nothing is booked yet: the patient confirms it with a button in the app.
    If nobody is logged in, it returns 'login_required' with a preview of the chosen slot.

    Args:
        department_id: The department's id, for example 'cardiology'.
        date: The date in YYYY-MM-DD format.
        time: A free slot time from check_available_slots, for example '09:30'.

    Returns:
        An action_id and the exact summary to confirm, 'login_required', or an error.
    """
    moment = common.now()
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
    patient = common.current_patient(tool_context)
    if patient is None:   # slot sahi hai; login ke baad wahi slot dobara maanga ja sakta hai
        return _login_required({"department": dept.name, "department_id": dept.id, "date": day.isoformat(),
                                "weekday": day.strftime("%A"), "time": time})
    payload = {"slot_id": slot.slot_id, "patient_ref": patient["id"], "department_id": dept.id,
               "date": day.isoformat(), "time": time}
    summary = {"action": "book", "patient_name": patient["full_name"], "phone": mask_phone(patient["phone"]),
               "department": dept.name, "location": f"{dept.building}, floor {dept.floor}",
               "date": day.isoformat(), "weekday": day.strftime("%A"), "time": time}
    return create_pending_action("book", payload, summary, tool_context)


@feature_required("appointments")
def my_appointments(tool_context: ToolContext) -> dict:
    """Lists the LOGGED-IN patient's own appointments (reference, department, date, time, status).
    Works only with a login; a name, phone or ID typed in the chat is ignored.

    Returns:
        The patient's appointments, or 'login_required'.
    """
    patient = common.current_patient(tool_context)
    if patient is None:
        return _login_required()
    try:
        bookings = his.get_his().list_for_patient(patient["id"])
    except his.HISError:
        return error(HIS_DOWN)
    return {"status": "ok", "appointments": [appointment_view(b) for b in bookings]}


def appointment_view(booking: his.Booking) -> dict:
    """Patient ko dikhane layak roop. Patient ID ya phone yahan nahin."""
    dept = get_department(booking.department_id)
    return {"appointment_id": booking.reference, "department": dept.name if dept else booking.department_id,
            "location": f"{dept.building}, floor {dept.floor}" if dept else "", "date": booking.date,
            "weekday": Date.fromisoformat(booking.date).strftime("%A"), "time": booking.time,
            "status": booking.status}


@feature_required("appointments")
def request_cancellation(appointment_id: str, tool_context: ToolContext) -> dict:
    """Prepares the cancellation of one of the LOGGED-IN patient's appointments and returns a summary.
    Nothing is cancelled yet: the patient confirms it with a button in the app.

    Args:
        appointment_id: The booking reference, for example 'HIS-APT-001' or 'APT-1A2B3C'.

    Returns:
        An action_id and the exact summary to confirm, 'login_required', or an error.
    """
    patient = common.current_patient(tool_context)
    if patient is None:
        return _login_required()
    apt_id = appointment_id.strip().upper()
    try:
        booking = his.get_his().find_for_patient(patient["id"], apt_id)
    except his.HISError:
        return error(HIS_DOWN)
    if booking is None:   # anjaan ya doosre patient ka reference: ek hi jawab
        return error("Aapke account me is ID ki koi appointment nahin mili.")
    if booking.status != "confirmed":
        return error("Yeh appointment pehle hi cancel ho chuki hai.")
    payload = {"appointment_id": apt_id, "patient_ref": patient["id"]}
    summary = {"action": "cancel", "appointment_id": apt_id, "date": booking.date, "time": booking.time}
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
            db.finish_pending(conn, action_id, outcome, notifications.booked(existing))
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
    db.finish_pending(conn, action_id, outcome, notifications.booked(booking))   # reminder ka event, usi transaction me
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
