"""Appointments ka database (SQLite). Saara SQL isi file me, taaki baaki code ko database ki jaankari na chahiye."""

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

DB_PATH = os.environ.get("HOSPITAL_DB_PATH", "hospital.db")
IST = ZoneInfo("Asia/Kolkata")

SCHEMA = """
CREATE TABLE IF NOT EXISTS appointments (
    id            TEXT PRIMARY KEY,
    patient_name  TEXT NOT NULL,
    phone         TEXT NOT NULL,
    department_id TEXT NOT NULL,
    date          TEXT NOT NULL,   -- hamesha YYYY-MM-DD (canonical key)
    time          TEXT NOT NULL,   -- hamesha HH:MM
    status        TEXT NOT NULL DEFAULT 'booked',
    created_at    TEXT NOT NULL,
    idempotency_key TEXT,         -- request_id: jis arzi (action_id) se bani; retry par wahi booking milti hai
    patient_ref   TEXT,           -- registered patient ki ID (DEMO-...)
    slot_id       TEXT            -- SLOT-cardiology-20261123-0900
);
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot
    ON appointments (department_id, date, time) WHERE status = 'booked';

-- Naye patient ka registration (demo). Sirf zaroori jaankari; Aadhaar ya bimari ka itihaas nahin.
CREATE TABLE IF NOT EXISTS patients (
    id            TEXT PRIMARY KEY,   -- DEMO-XXXXXXXX (asli UHID hospital ka system deta hai)
    full_name     TEXT NOT NULL,
    age           INTEGER NOT NULL,
    gender        TEXT NOT NULL,
    phone         TEXT NOT NULL,
    city          TEXT NOT NULL,
    guardian_name TEXT,               -- 18 se kam umar ho to zaroori
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_patient_per_phone_and_name ON patients (phone, full_name);

-- Login (demo): Patient ID + phone par ek baar ka code (OTP). Code ka sirf hash rakha jaata hai.
CREATE TABLE IF NOT EXISTS login_codes (
    patient_id  TEXT PRIMARY KEY,
    code_hash   TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0
);

-- Server-side login session. Browser ke paas sirf cookie me random token; yahan uska hash.
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash  TEXT PRIMARY KEY,
    patient_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);

-- Booking, cancel ya registration ki "arzi" jo patient ke Confirm button ka intezaar kar rahi hai.
CREATE TABLE IF NOT EXISTS pending_actions (
    id                 TEXT PRIMARY KEY,
    kind               TEXT NOT NULL,              -- 'book', 'cancel' ya 'register'
    payload            TEXT NOT NULL,              -- JSON: kya karna hai
    user_id            TEXT NOT NULL,              -- kisne maanga
    session_id         TEXT NOT NULL,              -- kis baat-cheet me
    created_invocation TEXT NOT NULL,              -- kis turn me bani
    expires_at         TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending',   -- pending / committing / done / failed / discarded
    outcome            TEXT                        -- JSON: nateeja, taaki retry par wahi laute
);
"""


class ActionAlreadyUsed(Exception):
    """Pending action pehle hi istemaal ho chuka hai."""


@contextmanager
def connect(db_path: str | None = None):
    """Connection kholta hai aur kaam ke baad HAMESHA band karta hai."""
    conn = sqlite3.connect(db_path or DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    try:
        yield conn
    finally:
        conn.close()


def _migrate(conn) -> None:
    """Purane hospital.db me naya column jodta hai (data nahin mitta)."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(appointments)")}
    for column in ("idempotency_key", "patient_ref", "slot_id"):
        if column not in columns:
            conn.execute(f"ALTER TABLE appointments ADD COLUMN {column} TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_key ON appointments (idempotency_key)")
    conn.commit()


def now_text() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")


def new_appointment_id() -> str:
    return "APT-" + uuid.uuid4().hex[:6].upper()


def booked_times(conn: sqlite3.Connection, department_id: str, date: str) -> set[str]:
    rows = conn.execute(
        "SELECT time FROM appointments WHERE department_id = ? AND date = ? AND status = 'booked'",
        (department_id, date),
    ).fetchall()
    return {r["time"] for r in rows}


def get_appointment(conn, appointment_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM appointments WHERE id = ?", (appointment_id,)).fetchone()


def count_future_bookings(conn, department_id: str, from_date: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM appointments "
        "WHERE department_id = ? AND date >= ? AND status = 'booked'",
        (department_id, from_date),
    ).fetchone()
    return row["n"]


# ---------- pending actions ----------

def create_pending(conn, kind: str, payload: dict, user_id: str, session_id: str,
                   invocation_id: str, expires_at: str) -> str:
    action_id = "ACT-" + uuid.uuid4().hex[:8].upper()
    with conn:
        conn.execute(
            "INSERT INTO pending_actions (id, kind, payload, user_id, session_id, created_invocation, expires_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (action_id, kind, json.dumps(payload, ensure_ascii=False), user_id, session_id,
             invocation_id, expires_at),
        )
    return action_id


def get_pending(conn, action_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM pending_actions WHERE id = ?", (action_id,)).fetchone()


def _consume(conn, action_id: str, outcome: dict) -> None:
    """Action ko 'done' karta hai. Sirf ek hi baar ho sakta hai."""
    cur = conn.execute(
        "UPDATE pending_actions SET status = 'done', outcome = ? WHERE id = ? AND status = 'pending'",
        (json.dumps(outcome, ensure_ascii=False), action_id),
    )
    if cur.rowcount != 1:
        raise ActionAlreadyUsed(action_id)


def fail_pending(conn, action_id: str, outcome: dict) -> None:
    with conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'failed', outcome = ? "
            "WHERE id = ? AND status IN ('pending', 'committing')",
            (json.dumps(outcome, ensure_ascii=False), action_id),
        )


def discard_pending(conn, action_id: str, outcome: dict) -> bool:
    """Sirf 'pending' arzi hatayi ja sakti hai; HIS ko bheji ja chuki arzi nahin."""
    with conn:
        cur = conn.execute(
            "UPDATE pending_actions SET status = 'discarded', outcome = ? WHERE id = ? AND status = 'pending'",
            (json.dumps(outcome, ensure_ascii=False), action_id),
        )
    return cur.rowcount == 1


def mark_committing(conn, action_id: str) -> bool:
    """Arzi ko 'committing' karta hai: HIS ko bheji ja rahi hai. Pehle se committing ho to bhi True (retry)."""
    with conn:
        cur = conn.execute(
            "UPDATE pending_actions SET status = 'committing' WHERE id = ? AND status IN ('pending', 'committing')",
            (action_id,),
        )
    return cur.rowcount == 1


def finish_pending(conn, action_id: str, outcome: dict) -> None:
    """HIS ne kaam pakka kar diya: arzi 'done', nateeja saath me."""
    with conn:
        conn.execute(
            "UPDATE pending_actions SET status = 'done', outcome = ? "
            "WHERE id = ? AND status IN ('pending', 'committing')",
            (json.dumps(outcome, ensure_ascii=False), action_id),
        )


# ---------- appointments (LocalHIS inhe istemaal karta hai) ----------

def find_appointment_by_key(conn, key: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM appointments WHERE idempotency_key = ?", (key,)).fetchone()


def insert_appointment(conn, appointment_id: str, key: str, p: dict) -> None:
    with conn:
        conn.execute(
            "INSERT INTO appointments (id, patient_name, phone, department_id, date, time, created_at, "
            "idempotency_key, patient_ref, slot_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (appointment_id, p["patient_name"], p["phone"], p["department_id"], p["date"], p["time"],
             now_text(), key, p["patient_ref"], p["slot_id"]),
        )


def cancel_appointment(conn, appointment_id: str, patient_ref: str) -> bool:
    """Maalik (patient ID) dekh kar cancel. Pehle se cancelled ho to bhi True (retry safe)."""
    with conn:
        cur = conn.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = ? AND patient_ref = ?",
            (appointment_id, patient_ref),
        )
    return cur.rowcount == 1


# ---------- patients ----------

def new_patient_id() -> str:
    return "DEMO-" + uuid.uuid4().hex[:8].upper()


def find_patient(conn, phone: str, full_name: str) -> sqlite3.Row | None:
    """Naam me chhote-bade akshar aur faltu space ka farq nahin: 'varun  singh' = 'Varun Singh'."""
    name = " ".join(full_name.split()).lower()
    for row in conn.execute("SELECT * FROM patients WHERE phone = ? ORDER BY created_at", (phone,)):
        if " ".join(row["full_name"].split()).lower() == name:
            return row
    return None


def get_patient(conn, patient_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()


def commit_registration(conn, action_id: str, patient_id: str, p: dict, outcome: dict) -> None:
    """EK transaction me: action consume + patient insert."""
    with conn:
        _consume(conn, action_id, outcome)
        conn.execute(
            "INSERT INTO patients (id, full_name, age, gender, phone, city, guardian_name, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (patient_id, p["full_name"], p["age"], p["gender"], p["phone"], p["city"], p.get("guardian_name"),
             now_text()),
        )


# ---------- login (auth.py inhe istemaal karta hai) ----------

def save_login_code(conn, patient_id: str, code_hash: str, expires_at: str) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO login_codes (patient_id, code_hash, expires_at, attempts) "
                     "VALUES (?, ?, ?, 0)", (patient_id, code_hash, expires_at))


def get_login_code(conn, patient_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM login_codes WHERE patient_id = ?", (patient_id,)).fetchone()


def count_login_attempt(conn, patient_id: str) -> None:
    with conn:
        conn.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE patient_id = ?", (patient_id,))


def delete_login_code(conn, patient_id: str) -> None:
    with conn:
        conn.execute("DELETE FROM login_codes WHERE patient_id = ?", (patient_id,))


def create_auth_session(conn, token_hash: str, patient_id: str, expires_at: str) -> None:
    with conn:
        conn.execute("INSERT INTO auth_sessions (token_hash, patient_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
                     (token_hash, patient_id, now_text(), expires_at))


def get_auth_session(conn, token_hash: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM auth_sessions WHERE token_hash = ? AND revoked = 0", (token_hash,)).fetchone()


def revoke_auth_session(conn, token_hash: str) -> None:
    with conn:
        conn.execute("UPDATE auth_sessions SET revoked = 1 WHERE token_hash = ?", (token_hash,))


def list_appointments_for_patient(conn, patient_ref: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM appointments WHERE patient_ref = ? ORDER BY date, time",
                        (patient_ref,)).fetchall()


def find_appointment_for_patient(conn, patient_ref: str, appointment_id: str) -> sqlite3.Row | None:
    """Reference aur maalik dono ek hi query me: doosre patient ka reference ho to kuch nahin milta."""
    return conn.execute("SELECT * FROM appointments WHERE id = ? AND patient_ref = ?",
                        (appointment_id, patient_ref)).fetchone()
