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
    slot_id       TEXT,           -- SLOT-cardiology-20261123-0900
    version       INTEGER NOT NULL DEFAULT 1   -- har badlaav par +1 (purana preview pakadne ke liye)
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

-- Reschedule (Lesson 6): har request_id ek hi baar laagu hota hai (double click / retry par wahi nateeja).
CREATE TABLE IF NOT EXISTS reschedule_requests (
    request_id  TEXT PRIMARY KEY,
    reference   TEXT NOT NULL,
    new_slot_id TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

-- Reception ki kaam ki line: jo kaam system khud nahin kar sakta (jaise HIS me reschedule ka API nahin).
CREATE TABLE IF NOT EXISTS reception_queue (
    id          TEXT PRIMARY KEY,      -- REQ-...
    kind        TEXT NOT NULL,         -- 'reschedule'
    patient_ref TEXT NOT NULL,
    booking_ref TEXT NOT NULL,
    details     TEXT NOT NULL,         -- JSON: maanga gaya slot aur vikalp
    status      TEXT NOT NULL DEFAULT 'pending',   -- pending / in_review / resolved
    created_at  TEXT NOT NULL,
    action_id   TEXT,                  -- jis arzi se aaya (ek arzi = ek kaam)
    claimed_by  TEXT, claimed_at TEXT, -- kis staff ne uthaya
    resolved_by TEXT, resolved_at TEXT,
    resolution  TEXT,                  -- changed / changed_manually / declined / verified_done / verified_not_done
    patient_message TEXT               -- patient ko dashboard par kya dikhe
);

-- Hospital staff (demo). Role 'reception' hi work queue khol sakta hai.
CREATE TABLE IF NOT EXISTS staff (
    id     TEXT PRIMARY KEY,           -- STAFF-...
    name   TEXT NOT NULL,
    phone  TEXT NOT NULL,
    role   TEXT NOT NULL,              -- 'reception'
    active INTEGER NOT NULL DEFAULT 1
);

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
    revoked     INTEGER NOT NULL DEFAULT 0,
    role        TEXT NOT NULL DEFAULT 'patient'   -- 'patient' ya 'staff': patient session staff ka kaam nahin karta
);

-- Health records (demo). Asli hospital me lab tests Lab Information System se aur prescriptions medical-record
-- system se aate hain. Document hospital ka original PDF hai; model use na likhta hai na badalta hai.
CREATE TABLE IF NOT EXISTS lab_tests (
    id              TEXT PRIMARY KEY,      -- LAB-...
    patient_ref     TEXT NOT NULL,
    visit_ref       TEXT,
    test_name       TEXT NOT NULL,
    department_id   TEXT,
    ordered_on      TEXT NOT NULL,         -- YYYY-MM-DD
    status          TEXT NOT NULL,         -- ordered / sample_collected / processing / report_available
    report_released INTEGER NOT NULL DEFAULT 0,   -- source system ne patient ke liye release kiya?
    report_pdf      BLOB
);
CREATE TABLE IF NOT EXISTS prescriptions (
    id              TEXT PRIMARY KEY,      -- RX-...
    patient_ref     TEXT NOT NULL,
    visit_ref       TEXT NOT NULL,
    visit_date      TEXT NOT NULL,
    department_id   TEXT NOT NULL,
    doctor          TEXT NOT NULL,
    issued          INTEGER NOT NULL DEFAULT 1,   -- hospital ne issue kiya?
    document_pdf    BLOB
);

-- Lesson 8: notification outbox. Jab hospital ka pakka nateeja save hota hai, USI transaction me yahan ek event.
-- Worker baad me (restart ke baad bhi) ise patient ke inbox tak pahunchata hai.
CREATE TABLE IF NOT EXISTS notification_outbox (
    event_id        TEXT PRIMARY KEY,   -- tay naam (jaise appointment.rescheduled:ACT-...): ek badlaav = ek event
    event_type      TEXT NOT NULL,      -- appointment.rescheduled / reception.request_resolved /
                                        -- lab.report_released / appointment.reminder
    patient_ref     TEXT NOT NULL,
    record_ref      TEXT NOT NULL,      -- kaunsa record khulega (appointment, request, lab test)
    payload         TEXT NOT NULL DEFAULT '{}',
    status          TEXT NOT NULL DEFAULT 'pending',   -- pending / processing / delivered / skipped / failed
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,      -- kab bhejna hai (reminder: tay samay; retry: thoda baad)
    locked_until    TEXT,               -- worker ne uthaya; isse pehle koi aur nahin uthata
    last_error      TEXT,
    created_at      TEXT NOT NULL,
    processed_at    TEXT
);
-- Patient ka inbox. event_id UNIQUE: worker ek event do baar chalaye to bhi ek hi item.
CREATE TABLE IF NOT EXISTS patient_notifications (
    id          TEXT PRIMARY KEY,       -- NTF-...
    event_id    TEXT NOT NULL UNIQUE,
    patient_ref TEXT NOT NULL,
    event_type  TEXT NOT NULL,
    title_hi    TEXT NOT NULL, body_hi TEXT NOT NULL,   -- approved template se; record ki details nahin
    title_en    TEXT NOT NULL, body_en TEXT NOT NULL,
    destination TEXT NOT NULL,          -- JSON: {"view": "appointment", "id": "HIS-APT-001"} (protected page)
    created_at  TEXT NOT NULL,
    read_at     TEXT
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
    if "version" not in columns:
        conn.execute("ALTER TABLE appointments ADD COLUMN version INTEGER NOT NULL DEFAULT 1")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_key ON appointments (idempotency_key)")
    if "role" not in {row["name"] for row in conn.execute("PRAGMA table_info(auth_sessions)")}:
        conn.execute("ALTER TABLE auth_sessions ADD COLUMN role TEXT NOT NULL DEFAULT 'patient'")
    queue_columns = {row["name"] for row in conn.execute("PRAGMA table_info(reception_queue)")}
    for column in ("action_id", "claimed_by", "claimed_at", "resolved_by", "resolved_at", "resolution",
                   "patient_message"):
        if column not in queue_columns:
            conn.execute(f"ALTER TABLE reception_queue ADD COLUMN {column} TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS one_queue_item_per_action ON reception_queue (action_id)")
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


def finish_pending(conn, action_id: str, outcome: dict, events: list[dict] = ()) -> None:
    """HIS ne kaam pakka kar diya: arzi 'done', nateeja saath me. Notification events (outbox) ISI transaction
    me: nateeja save hua to event bhi; nahin hua to koi nahin."""
    with conn:
        cur = conn.execute(
            "UPDATE pending_actions SET status = 'done', outcome = ? "
            "WHERE id = ? AND status IN ('pending', 'committing')",
            (json.dumps(outcome, ensure_ascii=False), action_id),
        )
        if cur.rowcount == 1:
            for event in events:
                add_outbox_event(conn, event)


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


def create_auth_session(conn, token_hash: str, patient_id: str, expires_at: str, role: str = "patient") -> None:
    """patient_id column me login karne wale ki ID (patient ya staff); role batata hai kaun."""
    with conn:
        conn.execute("INSERT INTO auth_sessions (token_hash, patient_id, created_at, expires_at, role) "
                     "VALUES (?, ?, ?, ?, ?)", (token_hash, patient_id, now_text(), expires_at, role))


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


# ---------- health records (records.py inhe istemaal karta hai; har query patient tak simit) ----------

def list_lab_tests(conn, patient_ref: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, visit_ref, test_name, department_id, ordered_on, status, report_released "
                        "FROM lab_tests WHERE patient_ref = ? ORDER BY ordered_on DESC, id", (patient_ref,)).fetchall()


def get_lab_report(conn, patient_ref: str, test_id: str) -> sqlite3.Row | None:
    """Sirf apna, aur sirf released report. Doosre ka ya release nahin hua to None."""
    return conn.execute("SELECT * FROM lab_tests WHERE id = ? AND patient_ref = ? AND report_released = 1 "
                        "AND status = 'report_available' AND report_pdf IS NOT NULL",
                        (test_id, patient_ref)).fetchone()


def list_prescriptions(conn, patient_ref: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT id, visit_ref, visit_date, department_id, doctor FROM prescriptions "
                        "WHERE patient_ref = ? AND issued = 1 ORDER BY visit_date DESC, id", (patient_ref,)).fetchall()


def get_prescription(conn, patient_ref: str, prescription_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM prescriptions WHERE id = ? AND patient_ref = ? AND issued = 1 "
                        "AND document_pdf IS NOT NULL", (prescription_id, patient_ref)).fetchone()


def save_lab_test(conn, row: dict) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO lab_tests (id, patient_ref, visit_ref, test_name, department_id, "
                     "ordered_on, status, report_released, report_pdf) VALUES (:id, :patient_ref, :visit_ref, "
                     ":test_name, :department_id, :ordered_on, :status, :report_released, :report_pdf)", row)


def save_prescription(conn, row: dict) -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO prescriptions (id, patient_ref, visit_ref, visit_date, department_id, "
                     "doctor, issued, document_pdf) VALUES (:id, :patient_ref, :visit_ref, :visit_date, "
                     ":department_id, :doctor, :issued, :document_pdf)", row)


# ---------- reschedule (LocalHIS) aur reception queue ----------

def find_reschedule(conn, request_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reschedule_requests WHERE request_id = ?", (request_id,)).fetchone()


def reschedule_appointment(conn, request_id: str, reference: str, expected_version: int, new_slot_id: str,
                           date: str, time: str) -> bool:
    """EK transaction: booking ko naye slot par le jao (sirf agar version wahi ho) aur request_id yaad rakho.
    Naya slot kisi aur ka ho to unique index IntegrityError deta hai aur poora transaction wapas: purani booking
    jaisi thi waisi."""
    with conn:
        cur = conn.execute(
            "UPDATE appointments SET slot_id = ?, date = ?, time = ?, version = version + 1 "
            "WHERE id = ? AND version = ? AND status = 'booked'",
            (new_slot_id, date, time, reference, expected_version))
        if cur.rowcount != 1:
            return False
        conn.execute("INSERT INTO reschedule_requests (request_id, reference, new_slot_id, created_at) "
                     "VALUES (?, ?, ?, ?)", (request_id, reference, new_slot_id, now_text()))
    return True


def staff_move(conn, reference: str, new_slot_id: str, date: str, time: str) -> None:
    """Sirf demo/test: staff ne booking khud badli (version +1)."""
    with conn:
        conn.execute("UPDATE appointments SET slot_id = ?, date = ?, time = ?, version = version + 1 WHERE id = ?",
                     (new_slot_id, date, time, reference))


def add_to_reception_queue(conn, kind: str, patient_ref: str, booking_ref: str, details: dict,
                           action_id: str | None = None) -> str:
    """Naya kaam. Ek arzi (action_id) se ek hi kaam: dobara aaye to purana hi lautao."""
    if action_id:
        old = conn.execute("SELECT id FROM reception_queue WHERE action_id = ?", (action_id,)).fetchone()
        if old:
            return old["id"]
    item_id = "REQ-" + uuid.uuid4().hex[:8].upper()
    with conn:
        conn.execute("INSERT INTO reception_queue (id, kind, patient_ref, booking_ref, details, created_at, action_id, "
                     "patient_message) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (item_id, kind, patient_ref, booking_ref, json.dumps(details, ensure_ascii=False), now_text(),
                      action_id, "Reception review pending"))
    return item_id


def reception_queue(conn, status: str | None = None) -> list[sqlite3.Row]:
    if status:
        return conn.execute("SELECT * FROM reception_queue WHERE status = ? ORDER BY created_at", (status,)).fetchall()
    return conn.execute("SELECT * FROM reception_queue ORDER BY created_at").fetchall()


def get_queue_item(conn, item_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM reception_queue WHERE id = ?", (item_id,)).fetchone()


def claim_queue_item(conn, item_id: str, staff_id: str) -> bool:
    """Sirf 'pending' kaam uthaya ja sakta hai: do staff ek saath dabayein to ek hi ko milta hai."""
    with conn:
        cur = conn.execute("UPDATE reception_queue SET status = 'in_review', claimed_by = ?, claimed_at = ? "
                           "WHERE id = ? AND status = 'pending'", (staff_id, now_text(), item_id))
    return cur.rowcount == 1


def resolve_queue_item(conn, item_id: str, staff_id: str, resolution: str, patient_message: str,
                       events: list[dict] = ()) -> bool:
    """Sirf wahi staff band kar sakta hai jisne uthaya. Patient ki notification ka event isi transaction me."""
    with conn:
        cur = conn.execute("UPDATE reception_queue SET status = 'resolved', resolved_by = ?, resolved_at = ?, "
                           "resolution = ?, patient_message = ? WHERE id = ? AND status = 'in_review' "
                           "AND claimed_by = ?",
                           (staff_id, now_text(), resolution, patient_message, item_id, staff_id))
        if cur.rowcount == 1:
            for event in events:
                add_outbox_event(conn, event)
    return cur.rowcount == 1


def queue_items_for_patient(conn, patient_ref: str) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM reception_queue WHERE patient_ref = ? ORDER BY created_at DESC",
                        (patient_ref,)).fetchall()


def stuck_actions(conn, older_than: str) -> list[sqlite3.Row]:
    """HIS ko bheji gayi par nateeja saaf nahin ('committing') aur expiry ke baad bhi wahi: staff jaanchega."""
    return conn.execute("SELECT * FROM pending_actions WHERE status = 'committing' AND expires_at < ? "
                        "AND kind IN ('book', 'reschedule')", (older_than,)).fetchall()


# ---------- staff ----------

def get_staff(conn, staff_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM staff WHERE id = ? AND active = 1", (staff_id,)).fetchone()


def save_staff(conn, staff_id: str, name: str, phone: str, role: str = "reception") -> None:
    with conn:
        conn.execute("INSERT OR REPLACE INTO staff (id, name, phone, role, active) VALUES (?, ?, ?, ?, 1)",
                     (staff_id, name, phone, role))


# ---------- notifications (Lesson 8): outbox aur patient inbox ----------

def add_outbox_event(conn, event: dict) -> None:
    """Commit NAHIN karta: bulane wale ke transaction ka hissa. Wahi event_id dobara aaye to kuch nahin."""
    conn.execute("INSERT OR IGNORE INTO notification_outbox (event_id, event_type, patient_ref, record_ref, payload, "
                 "next_attempt_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                 (event["event_id"], event["event_type"], event["patient_ref"], event["record_ref"],
                  json.dumps(event.get("payload", {}), ensure_ascii=False), event["due_at"], now_text()))


def get_outbox_event(conn, event_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM notification_outbox WHERE event_id = ?", (event_id,)).fetchone()


def claim_due_events(conn, now: str, lease_until: str, limit: int) -> list[sqlite3.Row]:
    """Jinka samay aa gaya (ya jinka pichhla worker beech me ruk gaya), unhe uthao. Har event ek hi worker ko."""
    rows = conn.execute("SELECT event_id FROM notification_outbox WHERE (status = 'pending' AND next_attempt_at <= ?) "
                        "OR (status = 'processing' AND locked_until < ?) ORDER BY next_attempt_at LIMIT ?",
                        (now, now, limit)).fetchall()
    claimed = []
    for row in rows:
        with conn:
            cur = conn.execute("UPDATE notification_outbox SET status = 'processing', locked_until = ?, "
                               "attempts = attempts + 1 WHERE event_id = ? AND ((status = 'pending' AND "
                               "next_attempt_at <= ?) OR (status = 'processing' AND locked_until < ?))",
                               (lease_until, row["event_id"], now, now))
        if cur.rowcount == 1:
            claimed.append(get_outbox_event(conn, row["event_id"]))
    return claimed


def finish_event(conn, event_id: str, status: str, note: str | None = None) -> None:
    with conn:
        conn.execute("UPDATE notification_outbox SET status = ?, locked_until = NULL, last_error = ?, processed_at = ? "
                     "WHERE event_id = ?", (status, note, now_text(), event_id))


def retry_event(conn, event_id: str, next_attempt_at: str, error: str, give_up: bool) -> None:
    with conn:
        conn.execute("UPDATE notification_outbox SET status = ?, locked_until = NULL, next_attempt_at = ?, "
                     "last_error = ? WHERE event_id = ?",
                     ("failed" if give_up else "pending", next_attempt_at, error[:300], event_id))


def insert_notification(conn, row: dict) -> tuple[sqlite3.Row, bool]:
    """Inbox me item. Is event_id ka item pehle se ho to wahi (naya nahin). (item, naya_bana?)"""
    with conn:
        cur = conn.execute("INSERT OR IGNORE INTO patient_notifications (id, event_id, patient_ref, event_type, "
                           "title_hi, body_hi, title_en, body_en, destination, created_at) VALUES (:id, :event_id, "
                           ":patient_ref, :event_type, :title_hi, :body_hi, :title_en, :body_en, :destination, "
                           ":created_at)", row)
    item = conn.execute("SELECT * FROM patient_notifications WHERE event_id = ?", (row["event_id"],)).fetchone()
    return item, cur.rowcount == 1


def list_notifications(conn, patient_ref: str, limit: int = 50) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM patient_notifications WHERE patient_ref = ? ORDER BY created_at DESC, id DESC "
                        "LIMIT ?", (patient_ref, limit)).fetchall()


def mark_notification_read(conn, patient_ref: str, notification_id: str) -> sqlite3.Row | None:
    """Sirf apni notification. Doosre ki ID: None (anjaan ID jaisa hi jawab)."""
    with conn:
        conn.execute("UPDATE patient_notifications SET read_at = COALESCE(read_at, ?) WHERE id = ? AND patient_ref = ?",
                     (now_text(), notification_id, patient_ref))
    return conn.execute("SELECT * FROM patient_notifications WHERE id = ? AND patient_ref = ?",
                        (notification_id, patient_ref)).fetchone()


def release_lab_report(conn, test_id: str, report_pdf: bytes, event: dict) -> bool:
    """Lab system ne report release ki: record aur notification event EK transaction me."""
    with conn:
        cur = conn.execute("UPDATE lab_tests SET status = 'report_available', report_released = 1, report_pdf = ? "
                           "WHERE id = ? AND report_released = 0", (report_pdf, test_id))
        if cur.rowcount == 1:
            add_outbox_event(conn, event)
    return cur.rowcount == 1


def get_lab_test(conn, test_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM lab_tests WHERE id = ?", (test_id,)).fetchone()


def outbox_status(conn, event_ids: list[str]) -> str | None:
    """In event_ids me se jo bana ho uski sthiti (staff ko: patient tak update pahuncha ya nahin)."""
    row = conn.execute(f"SELECT status FROM notification_outbox WHERE event_id IN ({','.join('?' * len(event_ids))}) "
                       "LIMIT 1", event_ids).fetchone()
    return row["status"] if row else None


def open_queue_item(conn, kind: str, patient_ref: str, booking_ref: str) -> sqlite3.Row | None:
    """Isi patient ki isi booking ka khula (pending / in_review) kaam, agar ho."""
    return conn.execute("SELECT * FROM reception_queue WHERE kind = ? AND patient_ref = ? AND booking_ref = ? "
                        "AND status IN ('pending', 'in_review') ORDER BY created_at LIMIT 1",
                        (kind, patient_ref, booking_ref)).fetchone()


def update_queue_request(conn, item_id: str, details: dict) -> None:
    """Patient ne usi appointment ke liye naya samay maanga: wahi kaam, nayi jaankari (pehli arzi ki id rehti hai)."""
    old = json.loads(get_queue_item(conn, item_id)["details"])
    details = {**details, "action_id": old.get("action_id"), "earlier_requests": old.get("earlier_requests", [])
               + [old.get("requested")]}
    with conn:
        conn.execute("UPDATE reception_queue SET details = ? WHERE id = ?",
                     (json.dumps(details, ensure_ascii=False), item_id))
