"""Fake HIS (hospital scheduler) sandbox: alag port par chalne wali local API.

    python -m his_sandbox                 # http://127.0.0.1:8900   Swagger: http://127.0.0.1:8900/docs

Teen mukhya endpoints (Lesson 3 ka contract):
    GET  /v1/slots?department_id=&date=          khaali slot, har ek ka slot_id
    POST /v1/bookings  {slot_id, patient_ref, request_id}
                                                 201 confirmed + booking_ref, ya 409 slot_unavailable
    GET  /v1/bookings/by-request/{request_id}    is attempt ki booking (timeout ke baad recovery)
Lesson 6: POST /v1/bookings/{booking_ref}/reschedule aur GET /v1/reschedules/by-request/{request_id}

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
    status        TEXT NOT NULL DEFAULT 'confirmed',
    version       INTEGER NOT NULL DEFAULT 1   -- har badlaav par +1
);
-- Reschedule ki har request_id ek hi baar laagu (double click / retry par wahi nateeja)
CREATE TABLE IF NOT EXISTS reschedules (
    request_id  TEXT PRIMARY KEY,
    booking_ref TEXT NOT NULL,
    new_slot_id TEXT NOT NULL
);
-- capacity 1: ek slot par ek hi confirmed booking
CREATE UNIQUE INDEX IF NOT EXISTS one_booking_per_slot ON bookings (slot_id) WHERE status = 'confirmed';
"""
FIELDS = ("booking_ref", "status", "slot_id", "patient_ref", "department_id", "date", "time", "version")


class BookingIn(BaseModel):
    slot_id: str = Field(examples=["SLOT-cardiology-20261123-0900"])
    patient_ref: str = Field(min_length=4, max_length=40, examples=["DEMO-PATIENT-001"])
    request_id: str = Field(min_length=4, max_length=64, examples=["BOOK-REQ-001"])


class CancelIn(BaseModel):
    patient_ref: str


class RescheduleIn(BaseModel):
    request_id: str = Field(min_length=4, max_length=64, examples=["RESCHED-REQ-001"])
    patient_ref: str = Field(min_length=4, max_length=40, examples=["DEMO-PATIENT-A"])
    expected_version: int = Field(ge=1, examples=[1])
    new_slot_id: str = Field(examples=["SLOT-cardiology-20261127-1430"])


class StaffMove(BaseModel):
    booking_ref: str
    new_slot_id: str


class Faults(BaseModel):
    lose_response_after_commit: int = Field(0, ge=0, description="Agli N bookings: commit karo, phir jawab der se do")
    delay_seconds: float = Field(5.0, ge=0, le=60)
    reschedule_unsupported: bool = Field(False, description="Asli HIS jaisa jisme reschedule ka API nahin (501)")


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
        if "version" not in {c["name"] for c in conn.execute("PRAGMA table_info(bookings)")}:
            conn.execute("ALTER TABLE bookings ADD COLUMN version INTEGER NOT NULL DEFAULT 1")   # purana db
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
        lose_response_maybe()
        return JSONResponse(as_json(row), status_code=201)

    def lose_response_maybe():
        with lock:
            lose = faults.lose_response_after_commit > 0
            if lose:
                faults.lose_response_after_commit -= 1
        if lose:   # kaam ho chuka hai, par jawab client ke timeout ke baad pahunchega
            clock.sleep(faults.delay_seconds)

    @app.post("/v1/bookings/{booking_ref}/reschedule", tags=["scheduler"])
    def reschedule(booking_ref: str, body: RescheduleIn):
        """EK transaction: purani booking jaancho (maalik, confirmed, version), naya slot lo, booking badlo.
        Naya slot na mile (409) to kuch nahin badalta. Version alag (412) = preview ke baad booking badal gayi.
        Reference wahi rehta hai. Wahi request_id dobara = wahi nateeja."""
        if faults.reschedule_unsupported:
            return JSONResponse({"status": "not_supported"}, status_code=501)
        parsed = roster.parse_slot_id(body.new_slot_id)
        if parsed is None or not roster.is_scheduled(body.new_slot_id):
            return JSONResponse({"status": "slot_unavailable", "reason": "unknown_slot"}, status_code=409)
        dept, date, time = parsed
        with connect() as conn:
            done = conn.execute("SELECT * FROM reschedules WHERE request_id = ?", (body.request_id,)).fetchone()
            if done is not None:
                if (done["booking_ref"], done["new_slot_id"]) != (booking_ref, body.new_slot_id):
                    raise HTTPException(422, "request_id pehle kisi aur badlaav ke liye istemaal hui")
                row = conn.execute("SELECT * FROM bookings WHERE booking_ref = ?", (booking_ref,)).fetchone()
                return JSONResponse(as_json(row), status_code=200)
            row = conn.execute("SELECT * FROM bookings WHERE booking_ref = ? AND patient_ref = ?",
                               (booking_ref, body.patient_ref)).fetchone()
            if row is None:
                raise HTTPException(404, "not_found")
            if row["status"] != "confirmed" or row["version"] != body.expected_version:
                return JSONResponse({"status": "stale", "booking": as_json(row)}, status_code=412)
            if row["department_id"] != dept:
                return JSONResponse({"status": "slot_unavailable", "reason": "other_department"}, status_code=409)
            try:
                with conn:   # target slot claim + booking update + request yaad: sab ek saath, ya kuch nahin
                    cur = conn.execute(
                        "UPDATE bookings SET slot_id = ?, date = ?, time = ?, version = version + 1 "
                        "WHERE booking_ref = ? AND version = ? AND status = 'confirmed'",
                        (body.new_slot_id, date, time, booking_ref, body.expected_version))
                    if cur.rowcount != 1:
                        raise sqlite3.IntegrityError("stale")
                    conn.execute("INSERT INTO reschedules (request_id, booking_ref, new_slot_id) VALUES (?, ?, ?)",
                                 (body.request_id, booking_ref, body.new_slot_id))
            except sqlite3.IntegrityError:
                return JSONResponse({"status": "slot_unavailable", "reason": "already_booked"}, status_code=409)
            row = conn.execute("SELECT * FROM bookings WHERE booking_ref = ?", (booking_ref,)).fetchone()
        lose_response_maybe()
        return JSONResponse(as_json(row), status_code=200)

    @app.get("/v1/reschedules/by-request/{request_id}", tags=["scheduler"])
    def reschedule_by_request(request_id: str):
        """Timeout ke baad: kya is request_id ka reschedule hua? Hua ho to booking ki abhi ki haalat."""
        with connect() as conn:
            done = conn.execute("SELECT * FROM reschedules WHERE request_id = ?", (request_id,)).fetchone()
            row = done and conn.execute("SELECT * FROM bookings WHERE booking_ref = ?",
                                        (done["booking_ref"],)).fetchone()
        if not row:
            raise HTTPException(404, "not_found")
        return as_json(row)

    @app.get("/v1/bookings/by-request/{request_id}", tags=["scheduler"])
    def find_by_request(request_id: str):
        """Timeout ke baad: kya is attempt ki booking HIS me bani? Bani ho to wahi reference."""
        with connect() as conn:
            row = by_request(conn, request_id)
        if row is None:
            raise HTTPException(404, "not_found")
        return as_json(row)

    @app.get("/v1/patients/{patient_ref}/bookings", tags=["patient records"])
    def list_for_patient(patient_ref: str):
        """Sirf is patient ki bookings."""
        with connect() as conn:
            rows = conn.execute("SELECT * FROM bookings WHERE patient_ref = ? ORDER BY date, time",
                                (patient_ref,)).fetchall()
        return {"patient_ref": patient_ref, "bookings": [as_json(r) for r in rows]}

    @app.get("/v1/patients/{patient_ref}/bookings/{booking_ref}", tags=["patient records"])
    def find_for_patient(patient_ref: str, booking_ref: str):
        """Reference + maalik ek hi query me. Doosre patient ka reference ho to wahi 404 jo anjaan reference par."""
        with connect() as conn:
            row = conn.execute("SELECT * FROM bookings WHERE booking_ref = ? AND patient_ref = ?",
                               (booking_ref, patient_ref)).fetchone()
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
            faults.reschedule_unsupported = new.reschedule_unsupported
        return faults

    @app.get("/_sandbox/bookings", tags=["sandbox"])
    def all_bookings(slot_id: str):
        """Ek slot par HIS me kitni bookings hain (demo me 'sirf ek' dikhane ke liye)."""
        with connect() as conn:
            rows = conn.execute("SELECT * FROM bookings WHERE slot_id = ?", (slot_id,)).fetchall()
        return [as_json(r) | {"request_id": r["request_id"]} for r in rows]

    @app.post("/_sandbox/staff-move", tags=["sandbox"])
    def staff_move(move: StaffMove):
        """Demo/test: staff ne appointment khud doosre slot par daal di (version +1)."""
        dept, date, time = roster.parse_slot_id(move.new_slot_id)
        with connect() as conn, conn:
            conn.execute("UPDATE bookings SET slot_id = ?, date = ?, time = ?, version = version + 1 "
                         "WHERE booking_ref = ?", (move.new_slot_id, date, time, move.booking_ref))
        return {"ok": True}

    @app.post("/_sandbox/reset", tags=["sandbox"])
    def reset():
        with connect() as conn, conn:
            conn.execute("DELETE FROM bookings")
        return {"ok": True}

    return app
