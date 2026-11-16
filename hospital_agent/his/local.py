"""LocalHIS: HIS ka contract, isi project ke SQLite par. Demo aur tests ke liye; koi network nahin."""

import sqlite3

from hospital_agent import db
from hospital_agent.his.base import Booking, BookingNotFound, SlotTaken


def _booking(row) -> Booking:
    return Booking(reference=row["id"], patient_name=row["patient_name"], phone=row["phone"],
                   department_id=row["department_id"], date=row["date"], time=row["time"],
                   status=row["status"])


class LocalHIS:
    def booked_times(self, department_id: str, date: str) -> set[str]:
        with db.connect() as conn:
            return db.booked_times(conn, department_id, date)

    def book(self, key, patient_name, phone, department_id, date, time) -> Booking:
        p = {"patient_name": patient_name, "phone": phone, "department_id": department_id,
             "date": date, "time": time}
        with db.connect() as conn:
            existing = db.find_appointment_by_key(conn, key)
            if existing is not None:
                return _booking(existing)
            try:
                db.insert_appointment(conn, db.new_appointment_id(), key, p)
            except sqlite3.IntegrityError as e:
                existing = db.find_appointment_by_key(conn, key)   # isi key ki doosri request jeet gayi
                if existing is not None:
                    return _booking(existing)
                raise SlotTaken(f"{department_id} {date} {time}") from e
            return _booking(db.find_appointment_by_key(conn, key))

    def find_by_key(self, key: str) -> Booking | None:
        with db.connect() as conn:
            row = db.find_appointment_by_key(conn, key)
        return _booking(row) if row else None

    def get_booking(self, reference: str) -> Booking | None:
        with db.connect() as conn:
            row = db.get_appointment(conn, reference)
        return _booking(row) if row else None

    def cancel(self, reference: str, phone: str) -> Booking:
        with db.connect() as conn:
            if not db.cancel_appointment(conn, reference, phone):
                raise BookingNotFound(reference)
            return _booking(db.get_appointment(conn, reference))
