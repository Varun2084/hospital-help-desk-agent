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
    created_at    TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot
    ON appointments (department_id, date, time) WHERE status = 'booked';

-- Booking ya cancel ki "arzi" jo patient ke 'haan' ka intezaar kar rahi hai.
CREATE TABLE IF NOT EXISTS pending_actions (
    id                 TEXT PRIMARY KEY,
    kind               TEXT NOT NULL,              -- 'book' ya 'cancel'
    payload            TEXT NOT NULL,              -- JSON: kya karna hai
    user_id            TEXT NOT NULL,              -- kisne maanga
    session_id         TEXT NOT NULL,              -- kis baat-cheet me
    created_invocation TEXT NOT NULL,              -- kis turn me bani
    expires_at         TEXT NOT NULL,
    status             TEXT NOT NULL DEFAULT 'pending',   -- pending / done / failed
    outcome            TEXT                        -- JSON: nateeja, taaki retry par wahi laute
);
"""


class ActionAlreadyUsed(Exception):
    """Pending action pehle hi istemaal ho chuka hai."""


class NothingToCancel(Exception):
    """ID + phone se koi 'booked' appointment nahin mili."""


@contextmanager
def connect(db_path: str | None = None):
    """Connection kholta hai aur kaam ke baad HAMESHA band karta hai."""
    conn = sqlite3.connect(db_path or DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


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
            "UPDATE pending_actions SET status = 'failed', outcome = ? WHERE id = ? AND status = 'pending'",
            (json.dumps(outcome, ensure_ascii=False), action_id),
        )


def commit_booking(conn, action_id: str, appointment_id: str, p: dict, outcome: dict) -> None:
    """EK transaction me: action consume + appointment insert. Koi ek fail ho to dono wapas (rollback)."""
    with conn:
        _consume(conn, action_id, outcome)
        conn.execute(
            "INSERT INTO appointments (id, patient_name, phone, department_id, date, time, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (appointment_id, p["patient_name"], p["phone"], p["department_id"], p["date"], p["time"],
             now_text()),
        )


def commit_cancellation(conn, action_id: str, appointment_id: str, phone: str, outcome: dict) -> None:
    """EK transaction me: maalik (phone) aur status dekh kar cancel + action consume."""
    with conn:
        cur = conn.execute(
            "UPDATE appointments SET status = 'cancelled' WHERE id = ? AND phone = ? AND status = 'booked'",
            (appointment_id, phone),
        )
        if cur.rowcount != 1:
            raise NothingToCancel(appointment_id)
        _consume(conn, action_id, outcome)
