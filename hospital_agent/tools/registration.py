"""Naye patient ka registration (demo). Booking jaisa hi do kadam ka flow:

  1. request_registration -> jaanch + sirf "pending action" (database nahin badalta)
  2. Confirm button       -> patient khud button dabata hai, tabhi patient record banta hai

Sirf zaroori jaankari li jaati hai. Aadhaar, bimari ka itihaas ya dawaiyan kabhi nahin.
Asli hospital me patient ID (UHID / ABHA) hospital ka system (HIS) deta hai; yahan DEMO- ID banti hai.
"""

import json
import re
import sqlite3
from datetime import datetime

from google.adk.tools import ToolContext

from hospital_agent import db
from hospital_agent.config import feature_required
from hospital_agent.safety import mask_phone
from hospital_agent.tools.common import PHONE_PATTERN, create_pending_action, error

GENDERS = {"male": "Male", "female": "Female", "other": "Other",
           "purush": "Male", "mahila": "Female", "पुरुष": "Male", "महिला": "Female", "अन्य": "Other"}
NAME_PATTERN = re.compile(r"^[^\d@#$%^&*_=+<>{}\[\]|\\/]{2,60}$")  # naam me ank ya chinh nahin
ADULT_AGE = 18


def _clean(text: str) -> str:
    return " ".join(text.split())


@feature_required("registration")
def request_registration(full_name: str, age: int, gender: str, phone: str, city: str,
                         tool_context: ToolContext, guardian_name: str = "") -> dict:
    """Prepares a new patient registration and returns a summary to read back to the patient.
    Nothing is saved yet: the patient confirms it with a button in the app.

    Args:
        full_name: The patient's full name.
        age: Age in completed years (0 to 120).
        gender: 'male', 'female' or 'other'.
        phone: A 10-digit Indian mobile number.
        city: Town or village and district, for example 'Rewa'.
        guardian_name: Required if the patient is under 18; the parent or guardian's name.

    Returns:
        An action_id and the summary to confirm, or an error.
    """
    name, city, guardian = _clean(full_name), _clean(city), _clean(guardian_name)
    if not NAME_PATTERN.fullmatch(name):
        return error("Patient ka poora naam sahi likhein (2 se 60 akshar, ank nahin).")
    if not isinstance(age, int) or not 0 <= age <= 120:
        return error("Umar 0 se 120 saal ke beech honi chahiye.")
    gender_key = GENDERS.get(gender.strip().lower())
    if gender_key is None:
        return error("Gender me 'male', 'female' ya 'other' likhein.")
    if not PHONE_PATTERN.fullmatch(phone):
        return error("Phone 10 ankon ka Indian mobile number hona chahiye (6, 7, 8 ya 9 se shuru).")
    if not 2 <= len(city) <= 60:
        return error("Shahar ya gaon ka naam likhein, jaise 'Rewa'.")
    if age < ADULT_AGE and not NAME_PATTERN.fullmatch(guardian):
        return error("18 saal se kam umar ke patient ke liye mata-pita ya guardian ka naam zaroori hai.")

    with db.connect() as conn:
        existing = db.find_patient(conn, phone, name)
    if existing is not None:
        return {"status": "already_registered", "patient_id": existing["id"], "phone": mask_phone(phone),
                "message": "Is naam aur phone se registration pehle se hai. Wahi patient ID istemaal karein."}

    payload = {"full_name": name, "age": age, "gender": gender_key, "phone": phone, "city": city,
               "guardian_name": guardian if age < ADULT_AGE else None}
    summary = {"action": "register", "full_name": name, "age": age, "gender": gender_key,
               "phone": mask_phone(phone), "city": city}
    if age < ADULT_AGE:
        summary["guardian_name"] = guardian
    result = create_pending_action("register", payload, summary, tool_context)
    result["consent_note"] = ("Yeh jaankari sirf registration aur appointment ke liye rakhi jaayegi. "
                              "Patient se poochhein ki kya woh iske liye sahmat hain.")
    return result


def complete_registration(conn, action_id: str, p: dict, moment: datetime) -> dict:
    """Confirm button (actions.confirm_pending) ise bulata hai."""
    patient_id = db.new_patient_id()
    outcome = {"status": "registered", "patient_id": patient_id, "full_name": p["full_name"],
               "phone": mask_phone(p["phone"]),
               "next_step": "Yeh patient ID likh lein. Appointment ke liye yahi ID aur phone batayein.",
               "note": "DEMO ID: asli hospital me registration counter ya HIS ki ID hi maanya hogi."}
    try:
        db.commit_registration(conn, action_id, patient_id, p, outcome)
    except sqlite3.IntegrityError:  # isi beech kisi ne wahi naam + phone register kar diya
        existing = db.find_patient(conn, p["phone"], p["full_name"])
        outcome = {"status": "already_registered", "patient_id": existing["id"], "phone": mask_phone(p["phone"])}
        db.fail_pending(conn, action_id, outcome)
    except db.ActionAlreadyUsed:
        return json.loads(db.get_pending(conn, action_id)["outcome"])
    return outcome
