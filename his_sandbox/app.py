"""HIS sandbox: slots, bookings, idempotency key, aur fault injection.

    python -m his_sandbox                 # http://127.0.0.1:8900
"""

import os
import sqlite3
import threading
import time as clock
from contextlib import contextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    seq             INTEGER PRIMARY KEY AUTOINCREMENT,
    reference       TEXT UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    patient_name    TEXT NOT NULL,
    phone           TEXT NOT NULL,
    department_id   TEXT NOT NULL,
    date            TEXT NOT NULL,
    time            TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'booked'
);
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot
    ON bookings (department_id, date, time) WHERE status = 'booked';
"""
FIELDS = ("reference", "patient_name", "phone", "department_id", "date", "time", "status")


class BookingIn(BaseModel):
    patient_name: str = Field(min_length=1, max_length=80)
    phone: str = Field(pattern=r"^[6-9]\d{9}$")
    department_id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


class CancelIn(BaseModel):
    phone: str


class Faults(BaseModel):
    lose_response_after_commit: int = Field(0, ge=0, description="Agli N bookings: commit karo, phir jawab der se do")
    delay_seconds: float = Field(5.0, ge=0, le=60)


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("HIS_SANDBOX_DB", "his_sandbox.db")
    app = FastAPI(title="HIS sandbox (synthetic)", docs_url="/docs")
    faults = Faults()
    lock = threading.Lock()

    @contextmanager
    def connect():
        conn = sqlite3.connect(db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
        try:
            yield conn
        finally:
            conn.close()

    def as_json(row) -> dict:
        return {k: row[k] for k in FIELDS}

    @app.get("/v1/slots/booked")
    def booked(department_id: str, date: str):
        with connect() as conn:
            rows = conn.execute("SELECT time FROM bookings WHERE department_id = ? AND date = ? AND status = 'booked'",
                                (department_id, date)).fetchall()
        return {"department_id": department_id, "date": date, "booked_times": sorted(r["time"] for r in rows)}

    @app.post("/v1/bookings")
    def book(body: BookingIn, idempotency_key: str = Header(min_length=4, max_length=64)):
        with connect() as conn:
            old = conn.execute("SELECT * FROM bookings WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if old is not None:   # wahi key dobara: wahi booking, nayi nahin
                if (old["department_id"], old["date"], old["time"], old["phone"]) != (
                        body.department_id, body.date, body.time, body.phone):
                    raise HTTPException(422, "idempotency key pehle kisi aur booking ke liye istemaal hui")
                return JSONResponse(as_json(old), status_code=200)
            try:
                with conn:
                    cur = conn.execute(
                        "INSERT INTO bookings (idempotency_key, patient_name, phone, department_id, date, time) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (idempotency_key, body.patient_name, body.phone, body.department_id, body.date, body.time))
                    conn.execute("UPDATE bookings SET reference = ? WHERE seq = ?",
                                 (f"HIS-{cur.lastrowid:06d}", cur.lastrowid))
            except sqlite3.IntegrityError:
                again = conn.execute("SELECT * FROM bookings WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
                if again is not None:
                    return JSONResponse(as_json(again), status_code=200)
                return JSONResponse({"error": "slot_taken"}, status_code=409)
            row = conn.execute("SELECT * FROM bookings WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        with lock:
            lose = faults.lose_response_after_commit > 0
            if lose:
                faults.lose_response_after_commit -= 1
        if lose:   # booking ho chuki hai, par jawab client ke timeout ke baad pahunchega
            clock.sleep(faults.delay_seconds)
        return JSONResponse(as_json(row), status_code=201)

    @app.get("/v1/bookings/by-key/{key}")
    def by_key(key: str):
        with connect() as conn:
            row = conn.execute("SELECT * FROM bookings WHERE idempotency_key = ?", (key,)).fetchone()
        if row is None:
            raise HTTPException(404, "not_found")
        return as_json(row)

    @app.get("/v1/bookings/{reference}")
    def get_booking(reference: str):
        with connect() as conn:
            row = conn.execute("SELECT * FROM bookings WHERE reference = ?", (reference,)).fetchone()
        if row is None:
            raise HTTPException(404, "not_found")
        return as_json(row)

    @app.post("/v1/bookings/{reference}/cancel")
    def cancel(reference: str, body: CancelIn):
        with connect() as conn:
            with conn:
                cur = conn.execute("UPDATE bookings SET status = 'cancelled' WHERE reference = ? AND phone = ?",
                                   (reference, body.phone))
            if cur.rowcount != 1:
                raise HTTPException(404, "not_found")
            return as_json(conn.execute("SELECT * FROM bookings WHERE reference = ?", (reference,)).fetchone())

    # ---- sirf sandbox: test aur demo ke liye switch ----
    @app.post("/_sandbox/faults")
    def set_faults(new: Faults):
        with lock:
            faults.lose_response_after_commit = new.lose_response_after_commit
            faults.delay_seconds = new.delay_seconds
        return faults

    @app.get("/_sandbox/bookings")
    def all_bookings(department_id: str, date: str, time: str):
        with connect() as conn:
            rows = conn.execute("SELECT * FROM bookings WHERE department_id = ? AND date = ? AND time = ?",
                                (department_id, date, time)).fetchall()
        return [as_json(r) | {"idempotency_key": r["idempotency_key"]} for r in rows]

    @app.post("/_sandbox/reset")
    def reset():
        with connect() as conn, conn:
            conn.execute("DELETE FROM bookings")
        return {"ok": True}

    return app
