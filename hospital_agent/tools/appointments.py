"""Appointment wale tools: khaali slot dekhna, booking/cancel ki arzi, aur patient ke 'haan' par pakka karna.

Booking do kadam me hoti hai:
  1. request_booking / request_cancellation  -> sirf ek "pending action" banta hai (database nahin badalta).
  2. confirm_action                          -> code khud jaanchta hai ki patient ne NAYE sandesh me 'haan' kaha,
                                                tabhi database me likhta hai.
Model ke arguments akele kuch book ya cancel nahin kar sakte.
"""

import json
import re
import sqlite3
from datetime import date as Date
from datetime import datetime, timedelta
from datetime import time as Time
from zoneinfo import ZoneInfo

from google.adk.tools import ToolContext

from hospital_agent import db
from hospital_agent.config import feature_required, get_department
from hospital_agent.safety import mask_phone
from hospital_agent.text_match import contains_keyword

IST = ZoneInfo("Asia/Kolkata")
BOOKING_WINDOW_DAYS = 30
CONFIRM_WINDOW_MINUTES = 10
PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")

YES_WORDS = ["yes", "haan", "han", "haa", "ji", "confirm", "confirmed", "ok", "okay", "theek hai",
             "thik hai", "kar do", "kar dijiye", "हाँ", "हां", "जी", "ठीक है", "कर दो", "कर दीजिए"]
NO_WORDS = ["no", "nahi", "nahin", "nhi", "mat", "ruko", "wait", "नहीं", "मत", "रुको"]


def now() -> datetime:
    """Bharat ke samay (IST) ka abhi ka waqt. Tests me ise badal (patch) kar koi bhi pal bana sakte hain."""
    return datetime.now(IST)


def today() -> Date:
    return now().date()


@feature_required("appointments")
def today_date() -> dict:
    """Returns today's date and weekday. Call this before working out dates like 'tomorrow' or 'next Monday'.

    Returns:
        Today's date in YYYY-MM-DD format and the weekday.
    """
    day = today()
    return {"today": day.isoformat(), "weekday": day.strftime("%A")}


def _error(message: str) -> dict:
    return {"status": "error", "message": message}


def parse_booking_date(value: str) -> Date:
    """Sirf YYYY-MM-DD chalega. '20261116' jaisa likhne par ValueError."""
    if not DATE_PATTERN.fullmatch(value.strip()):
        raise ValueError("Expected YYYY-MM-DD")
    return Date.fromisoformat(value.strip())


def is_future_slot(day: Date, hhmm: str, moment: datetime) -> bool:
    """Kya yeh slot 'moment' ke baad shuru hota hai?"""
    return datetime.combine(day, Time.fromisoformat(hhmm), tzinfo=IST) > moment


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _all_slots(opd_hours: str, slot_minutes: int) -> list[str]:
    start_s, end_s = opd_hours.split("-")
    current, end = _to_minutes(start_s), _to_minutes(end_s)
    slots = []
    while current + slot_minutes <= end:
        slots.append(f"{current // 60:02d}:{current % 60:02d}")
        current += slot_minutes
    return slots


def _check_department_and_date(department_id: str, date: str, moment: datetime):
    """Department aur tareekh ki jaanch. Sahi ho to (dept, day, None), galat ho to (None, None, error)."""
    dept = get_department(department_id)
    if dept is None or not dept.active:
        return None, None, _error(f"'{department_id}' me abhi OPD booking nahin ho sakti.")
    try:
        day = parse_booking_date(date)
    except ValueError:
        return None, None, _error("Tareekh YYYY-MM-DD format me dein, jaise 2026-11-20.")
    if day < moment.date():
        return None, None, _error("Beeti hui tareekh par booking nahin ho sakti.")
    if day > moment.date() + timedelta(days=BOOKING_WINDOW_DAYS):
        return None, None, _error(f"Booking sirf agle {BOOKING_WINDOW_DAYS} din tak ki ho sakti hai.")
    weekday = day.strftime("%a")
    if weekday not in dept.opd_days:
        return None, None, _error(
            f"{dept.name} ki OPD {weekday} ko nahin hoti. OPD ke din: {', '.join(dept.opd_days)}."
        )
    return dept, day, None


def _free_slots(dept, day: Date, moment: datetime) -> list[str]:
    """Woh slots jo schedule me hain, abhi ke baad shuru hote hain, aur booked nahin hain."""
    with db.connect() as conn:
        taken = db.booked_times(conn, dept.id, day.isoformat())
    return [s for s in _all_slots(dept.opd_hours, dept.slot_minutes)
            if s not in taken and is_future_slot(day, s, moment)]


@feature_required("appointments")
def check_available_slots(department_id: str, date: str) -> dict:
    """Shows free appointment times for a department on a date. Read-only.

    Args:
        department_id: The department's id, for example 'cardiology'.
        date: The date in YYYY-MM-DD format.

    Returns:
        The list of free times, or an error explaining why booking is not possible.
    """
    moment = now()  # ek request me ek hi 'abhi'
    dept, day, error = _check_department_and_date(department_id, date, moment)
    if error:
        return error
    return {"status": "ok", "department": dept.name, "date": day.isoformat(),
            "free_slots": _free_slots(dept, day, moment)}


def _owner(tool_context: ToolContext) -> tuple[str, str]:
    return tool_context.user_id, tool_context.session.id


def _pending(kind: str, payload: dict, summary: dict, tool_context: ToolContext, moment: datetime) -> dict:
    user_id, session_id = _owner(tool_context)
    expires_at = (moment + timedelta(minutes=CONFIRM_WINDOW_MINUTES)).isoformat(timespec="seconds")
    with db.connect() as conn:
        action_id = db.create_pending(conn, kind, payload, user_id, session_id,
                                      tool_context.invocation_id, expires_at)
    return {
        "status": "needs_confirmation",
        "action_id": action_id,
        "summary": summary,
        "valid_for_minutes": CONFIRM_WINDOW_MINUTES,
        "next_step": "Yeh summary patient ko padh kar sunayein aur poochhein: 'Kya main ise pakka karun?'. "
                     "Patient ke 'haan' kehne ke BAAD hi confirm_action bulayein.",
    }


@feature_required("appointments")
def request_booking(patient_name: str, phone: str, department_id: str, date: str, time: str,
                    tool_context: ToolContext) -> dict:
    """Prepares an OPD booking and returns a summary to read back to the patient.
    Nothing is booked yet. After the patient says yes, call confirm_action.

    Args:
        patient_name: The patient's full name.
        phone: A 10-digit Indian mobile number.
        department_id: The department's id, for example 'cardiology'.
        date: The date in YYYY-MM-DD format.
        time: A free slot time from check_available_slots, for example '09:30'.

    Returns:
        An action_id and the exact summary to confirm, or an error.
    """
    moment = now()
    name = patient_name.strip()
    if not name:
        return _error("Patient ka naam chahiye.")
    if not PHONE_PATTERN.fullmatch(phone):
        return _error("Phone 10 ankon ka Indian mobile number hona chahiye (6, 7, 8 ya 9 se shuru).")
    dept, day, error = _check_department_and_date(department_id, date, moment)
    if error:
        return error
    if time not in _all_slots(dept.opd_hours, dept.slot_minutes):
        return _error(f"{time} is department ka valid slot nahin hai. Pehle check_available_slots chalayein.")
    if time not in _free_slots(dept, day, moment):
        return _error(f"{time} ka slot ab khaali nahin hai (beet chuka ya booked). Doosra samay chunein.")
    payload = {"patient_name": name, "phone": phone, "department_id": dept.id,
               "date": day.isoformat(), "time": time}
    summary = {"action": "book", "patient_name": name, "phone": mask_phone(phone), "department": dept.name,
               "location": f"{dept.building}, floor {dept.floor}", "date": day.isoformat(), "time": time}
    return _pending("book", payload, summary, tool_context, moment)


@feature_required("appointments")
def request_cancellation(appointment_id: str, phone: str, tool_context: ToolContext) -> dict:
    """Prepares the cancellation of an appointment and returns a summary to read back.
    Nothing is cancelled yet. After the patient says yes, call confirm_action.

    Args:
        appointment_id: The id given at booking, for example 'APT-1A2B3C'.
        phone: The 10-digit mobile number used for the booking.

    Returns:
        An action_id and the exact summary to confirm, or an error.
    """
    apt_id = appointment_id.strip().upper()
    with db.connect() as conn:
        row = db.get_appointment(conn, apt_id)
    if row is None or row["phone"] != phone:
        return _error("Is ID aur phone number se koi appointment nahin mili.")
    if row["status"] != "booked":
        return _error("Yeh appointment pehle hi cancel ho chuki hai.")
    payload = {"appointment_id": apt_id, "phone": phone}
    summary = {"action": "cancel", "appointment_id": apt_id, "date": row["date"], "time": row["time"]}
    return _pending("cancel", payload, summary, tool_context, now())


def _user_said_yes(tool_context: ToolContext) -> bool:
    """Patient ke TAAZA sandesh me 'haan' jaisa shabd ho aur 'nahin' jaisa na ho."""
    content = tool_context.user_content
    text = " ".join(p.text for p in (content.parts if content else []) or [] if p.text)
    if any(contains_keyword(text, w) for w in NO_WORDS):
        return False
    return any(contains_keyword(text, w) for w in YES_WORDS)


@feature_required("appointments")
def confirm_action(action_id: str, tool_context: ToolContext) -> dict:
    """Completes a prepared booking or cancellation. Call it only after the patient has
    replied yes to the summary, in a new message.

    Args:
        action_id: The action_id returned by request_booking or request_cancellation.

    Returns:
        The final booking or cancellation details, or an error.
    """
    moment = now()
    user_id, session_id = _owner(tool_context)
    with db.connect() as conn:
        action = db.get_pending(conn, action_id.strip().upper())
        # 1. Action hai, aur usi patient + usi baat-cheet ka hai?
        if action is None or action["user_id"] != user_id or action["session_id"] != session_id:
            return _error("Yeh action nahin mila. Dobara request_booking ya request_cancellation chalayein.")
        # 2. Pehle hi ho chuka? Wahi purana nateeja lautao (retry se doosri booking nahin banti).
        if action["status"] != "pending":
            return json.loads(action["outcome"])
        # 3. Samay nikal gaya?
        if moment > datetime.fromisoformat(action["expires_at"]):
            outcome = _error("Confirm karne ka samay nikal gaya. Kripya dobara shuru karein.")
            db.fail_pending(conn, action["id"], outcome)
            return outcome
        # 4. Patient ne NAYE sandesh me haan kaha? (model usi turn me khud confirm nahin kar sakta)
        if tool_context.invocation_id == action["created_invocation"]:
            return _error("Pehle summary patient ko sunayein. Unke jawab ke baad hi confirm ho sakta hai.")
        if not _user_said_yes(tool_context):
            return _error("Patient ne saaf 'haan' nahin kaha. Summary dobara sunayein aur haan/nahin poochhein.")

        p = json.loads(action["payload"])
        if action["kind"] == "book":
            return _do_booking(conn, action["id"], p, moment)
        return _do_cancellation(conn, action["id"], p)


def _do_booking(conn, action_id: str, p: dict, moment: datetime) -> dict:
    dept = get_department(p["department_id"])
    day = Date.fromisoformat(p["date"])
    if dept is None or not dept.active or not is_future_slot(day, p["time"], moment):
        outcome = _error("Yeh slot ab uplabdh nahin hai. Doosra samay chunein.")
        db.fail_pending(conn, action_id, outcome)
        return outcome
    appointment_id = db.new_appointment_id()
    outcome = {
        "status": "booked",
        "appointment_id": appointment_id,
        "patient_name": p["patient_name"],
        "phone": mask_phone(p["phone"]),
        "department": dept.name,
        "location": f"{dept.building}, floor {dept.floor}",
        "date": p["date"],
        "time": p["time"],
        "reminder": "Registration card aur photo ID ke saath 30 minute pehle pahunchein.",
    }
    try:
        db.commit_booking(conn, action_id, appointment_id, p, outcome)
    except sqlite3.IntegrityError:  # unique index: slot kisi aur ne le liya
        outcome = _error(f"{p['time']} ka slot abhi-abhi kisi aur ne le liya. Doosra samay chunein.")
        db.fail_pending(conn, action_id, outcome)
    except db.ActionAlreadyUsed:
        return json.loads(db.get_pending(conn, action_id)["outcome"])
    return outcome


def _do_cancellation(conn, action_id: str, p: dict) -> dict:
    row = db.get_appointment(conn, p["appointment_id"])
    outcome = {"status": "cancelled", "appointment_id": p["appointment_id"],
               "date": row["date"], "time": row["time"]}
    try:
        db.commit_cancellation(conn, action_id, p["appointment_id"], p["phone"], outcome)
    except db.NothingToCancel:
        outcome = _error("Yeh appointment ab 'booked' nahin hai; cancel nahin hui.")
        db.fail_pending(conn, action_id, outcome)
    except db.ActionAlreadyUsed:
        return json.loads(db.get_pending(conn, action_id)["outcome"])
    return outcome
