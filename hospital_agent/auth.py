"""Patient login (authentication): "aap kaun hain?" ka jawab server tay karta hai, browser nahin.

Demo login: Patient ID + registered phone -> ek baar ka 6 ank ka code (OTP), 5 minute ke liye.
Asli hospital me yeh code SMS se jaata; demo me SMS gateway nahin, isliye code screen par dikhaya jaata hai.
Login ke baad browser ko HttpOnly cookie me ek random token milta hai. Server us token ke hash se patient
ID nikalta hai. Chat me likha naam, phone ya patient ID is pehchaan ko kabhi nahin badalta.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from hospital_agent import db
from hospital_agent.tools import common

CODE_MINUTES = 5
MAX_ATTEMPTS = 5
SESSION_HOURS = 8


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def start_login(patient_id: str, phone: str) -> dict:
    """Patient ID aur phone mel khayein to code banta hai. Na milein to ek hi saadharan jawab."""
    patient_id = patient_id.strip().upper()
    with db.connect() as conn:
        patient = db.get_patient(conn, patient_id)
        if patient is None or patient["phone"] != phone.strip():
            return {"status": "error", "message": "Patient ID ya phone number sahi nahin hai."}
    return _send_code(patient_id)


def start_staff_login(staff_id: str, phone: str) -> dict:
    """Staff ka login bhi wahi tareeka, par alag records (staff table) aur session par role 'staff'."""
    staff_id = staff_id.strip().upper()
    with db.connect() as conn:
        staff = db.get_staff(conn, staff_id)
        if staff is None or staff["phone"] != phone.strip():
            return {"status": "error", "message": "Staff ID ya phone number sahi nahin hai."}
    return _send_code(staff_id)


def _send_code(principal_id: str) -> dict:
    with db.connect() as conn:
        code = f"{secrets.randbelow(10**6):06d}"
        expires = (common.now() + timedelta(minutes=CODE_MINUTES)).isoformat(timespec="seconds")
        db.save_login_code(conn, principal_id, _hash(principal_id + ":" + code), expires)
    return {"status": "code_sent", "demo_code": code,
            "note": "Demo: asli app me yeh code SMS se aata. Yahan SMS nahin, isliye screen par dikh raha hai."}


def verify_login(patient_id: str, code: str, role: str = "patient") -> str | None:
    """Sahi code par naya session token (sirf ek baar browser ko). Galat, purana ya 5 baar galat ho to None.
    role: 'patient' ya 'staff'. Staff ka code patient login se (aur ulta) kaam nahin karta."""
    if patient_id.strip().upper().startswith("STAFF-") != (role == "staff"):
        return None
    patient_id = patient_id.strip().upper()
    with db.connect() as conn:
        row = db.get_login_code(conn, patient_id)
        if row is None or row["attempts"] >= MAX_ATTEMPTS:
            return None
        if common.now() > datetime.fromisoformat(row["expires_at"]):
            db.delete_login_code(conn, patient_id)
            return None
        if not hmac.compare_digest(row["code_hash"], _hash(patient_id + ":" + code.strip())):
            db.count_login_attempt(conn, patient_id)
            return None
        db.delete_login_code(conn, patient_id)   # code ek hi baar chalta hai
        token = secrets.token_urlsafe(32)
        expires = (common.now() + timedelta(hours=SESSION_HOURS)).isoformat(timespec="seconds")
        db.create_auth_session(conn, _hash(token), patient_id, expires, role)
    return token


def patient_for_token(token: str | None):
    """Cookie ke token se patient record, ya None (na token, galat, logout ho chuka, ya samay khatam)."""
    if not token:
        return None
    with db.connect() as conn:
        session = _live_session(conn, token, "patient")
        return db.get_patient(conn, session["patient_id"]) if session else None


def staff_for_token(token: str | None):
    """Cookie ke token se staff record, ya None. Patient ka session yahan kabhi nahin chalta."""
    if not token:
        return None
    with db.connect() as conn:
        session = _live_session(conn, token, "staff")
        return db.get_staff(conn, session["patient_id"]) if session else None


def _live_session(conn, token: str, role: str):
    session = db.get_auth_session(conn, _hash(token))
    if session is None or session["role"] != role or common.now() > datetime.fromisoformat(session["expires_at"]):
        return None
    return session


def logout(token: str | None) -> None:
    if token:
        with db.connect() as conn:
            db.revoke_auth_session(conn, _hash(token))
