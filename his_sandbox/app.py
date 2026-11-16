"""Fake HIS (hospital scheduler) sandbox: alag port par chalne wali local API.

    python -m his_sandbox                 # http://127.0.0.1:8900   Swagger: http://127.0.0.1:8900/docs

Teen mukhya endpoints (Lesson 3 ka contract):
    GET  /v1/slots?department_id=&date=          khaali slot, har ek ka slot_id
    POST /v1/bookings  {slot_id, patient_ref, request_id}
                                                 201 confirmed + booking_ref, ya 409 slot_unavailable
    GET  /v1/bookings/by-request/{request_id}    is attempt ki booking (timeout ke baad recovery)

Slot claim aur booking insert ek transaction me hote hain, aur ek slot par ek hi booking database ka
unique index pakka karta hai. Synthetic data hi istemaal karein; yeh kisi asli hospital ka system nahin.
"""

import os
import sqlite3
import threading
import time as clock
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from hospital_agent.his import slots as roster

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_ref   TEXT UNIQUE,
    request_id    TEXT NOT NULL UNIQUE,     -- ek booking attempt; retry par wahi
    slot_id       TEXT NOT NULL,
    patient_ref   TEXT NOT NULL,
    department_id TEXT NOT NULL,
    date          TEXT NOT NULL,
    time          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'confirmed'
);
-- capacity 1: ek slot par ek hi confirmed booking
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot ON bookings (slot_id) WHERE status = 'confirmed';
"""
FIELDS = ("booking_ref", "status", "slot_id", "patient_ref", "department_id", "date", "time")


class BookingIn(BaseModel):
    slot_id: str = Field(examples=["SLOT-cardiology-20261123-0900"])
    patient_ref: str = Field(min_length=4, max_length=40, examples=["DEMO-PATIENT-001"])
    request_id: str = Field(min_length=4, max_length=64, examples=["BOOK-REQ-001"])


class CancelIn(BaseModel):
    patient_ref: str


class Faults(BaseModel):
    lose_response_after_commit: int = Field(0, ge=0, description="Agli N bookings: commit karo, phir jawab der se do")
    delay_seconds: float = Field(5.0, ge=0, le=60)


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("HIS_SANDBOX_DB", "his_sandbox.db")
    app = FastAPI(title="Fake HIS scheduler (synthetic sandbox)", version="1.0", docs_url="/docs")
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

    def by_request(conn, request_id: str):
        return conn.execute("SELECT * FROM bookings WHERE request_id = ?", (request_id,)).fetchone()

    @app.get("/v1/slots", tags=["scheduler"])
    def open_slots(department_id: str = Query(examples=["cardiology"]),
                   date: str = Query(pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2026-11-23"])):
        """Us din ke khaali slot. Har slot ka slot_id booking ke waqt bhejna hai."""
        with connect() as conn:
            taken = {r["slot_id"] for r in conn.execute(
                "SELECT slot_id FROM bookings WHERE department_id = ? AND date = ? AND status = 'confirmed'",
                (department_id, date))}
        free = [{"slot_id": sid, "time": t, "status": "open"}
                for sid, t in roster.scheduled_slot_ids(department_id, date) if sid not in taken]
        return {"department_id": department_id, "date": date, "slots": free}

    @app.post("/v1/bookings", status_code=201, tags=["scheduler"])
    def book(body: BookingIn):
        """Slot book karta hai. Wahi request_id dobara aaye to nayi booking nahin, wahi purani milti hai."""
        parsed = roster.parse_slot_id(body.slot_id)
        if parsed is None or not roster.is_scheduled(body.slot_id):
            return JSONResponse({"status": "slot_unavailable", "slot_id": body.slot_id,
                                 "reason": "unknown_slot"}, status_code=409)
        dept, date, time = parsed
        with connect() as conn:
            old = by_request(conn, body.request_id)
            if old is not None:   # wahi attempt dobara: wahi booking
                if (old["slot_id"], old["patient_ref"]) != (body.slot_id, body.patient_ref):
                    raise HTTPException(422, "request_id pehle kisi aur booking ke liye istemaal hui")
                return JSONResponse(as_json(old), status_code=200)
            try:
                with conn:   # slot claim + booking insert: ek transaction
                    cur = conn.execute(
                        "INSERT INTO bookings (request_id, slot_id, patient_ref, department_id, date, time) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (body.request_id, body.slot_id, body.patient_ref, dept, date, time))
                    conn.execute("UPDATE bookings SET booking_ref = ? WHERE seq = ?",
                                 (f"HIS-APT-{cur.lastrowid:03d}", cur.lastrowid))
            except sqlite3.IntegrityError:
                again = by_request(conn, body.request_id)
                if again is not None:
                    return JSONResponse(as_json(again), status_code=200)
                return JSONResponse({"status": "slot_unavailable", "slot_id": body.slot_id,
                                     "reason": "already_booked"}, status_code=409)
            row = by_request(conn, body.request_id)
        with lock:
            lose = faults.lose_response_after_commit > 0
            if lose:
                faults.lose_response_after_commit -= 1
        if lose:   # booking ho chuki hai, par jawab client ke timeout ke baad pahunchega
            clock.sleep(faults.delay_seconds)
        return JSONResponse(as_json(row), status_code=201)

    @app.get("/v1/bookings/by-request/{request_id}", tags=["scheduler"])
    def find_by_request(request_id: str):
        """Timeout ke baad: kya is attempt ki booking HIS me bani? Bani ho to wahi reference."""
        with connect() as conn:
            row = by_request(conn, request_id)
        if row is None:
            raise HTTPException(404, "not_found")
        return as_json(row)

    @app.get("/v1/bookings/{booking_ref}", tags=["scheduler"])
    def get_booking(booking_ref: str):
        with connect() as conn:
            row = conn.execute("SELECT * FROM bookings WHERE booking_ref = ?", (booking_ref,)).fetchone()
        if row is None:
            raise HTTPException(404, "not_found")
        return as_json(row)

    @app.post("/v1/bookings/{booking_ref}/cancel", tags=["scheduler"])
    def cancel(booking_ref: str, body: CancelIn):
        with connect() as conn:
            with conn:
                cur = conn.execute("UPDATE bookings SET status = 'cancelled' WHERE booking_ref = ? AND patient_ref = ?",
                                   (booking_ref, body.patient_ref))
            if cur.rowcount != 1:
                raise HTTPException(404, "not_found")
            return as_json(conn.execute("SELECT * FROM bookings WHERE booking_ref = ?", (booking_ref,)).fetchone())

    # ---- sirf sandbox: test aur demo ke liye switch ----
    @app.post("/_sandbox/faults", tags=["sandbox"])
    def set_faults(new: Faults):
        """Fault injection: agli N bookings commit hongi, par jawab delay_seconds der se aayega."""
        with lock:
            faults.lose_response_after_commit = new.lose_response_after_commit
            faults.delay_seconds = new.delay_seconds
        return faults

    @app.get("/_sandbox/bookings", tags=["sandbox"])
    def all_bookings(slot_id: str):
        """Ek slot par HIS me kitni bookings hain (demo me 'sirf ek' dikhane ke liye)."""
        with connect() as conn:
            rows = conn.execute("SELECT * FROM bookings WHERE slot_id = ?", (slot_id,)).fetchall()
        return [as_json(r) | {"request_id": r["request_id"]} for r in rows]

    @app.post("/_sandbox/reset", tags=["sandbox"])
    def reset():
        with connect() as conn, conn:
            conn.execute("DELETE FROM bookings")
        return {"ok": True}

    return app
