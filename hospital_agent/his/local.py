"""LocalHIS: HIS ka contract, isi project ke SQLite par. Demo aur tests ke liye; koi network nahin."""

import sqlite3

from hospital_agent import db
from hospital_agent.his import slots
from hospital_agent.his.base import Booking, BookingNotFound, Slot, SlotTaken

STATUS = {"booked": "confirmed", "cancelled": "cancelled"}   # local table ke shabd -> HIS ke shabd


def _booking(row) -> Booking:
    return Booking(reference=row["id"], patient_ref=row["patient_ref"] or "",
                   slot_id=row["slot_id"] or slots.make_slot_id(row["department_id"], row["date"], row["time"]),
                   department_id=row["department_id"], date=row["date"], time=row["time"],
                   status=STATUS.get(row["status"], row["status"]))


class LocalHIS:
    def open_slots(self, department_id: str, date: str) -> list[Slot]:
        with db.connect() as conn:
            taken = db.booked_times(conn, department_id, date)
        return [Slot(sid, t) for sid, t in slots.scheduled_slot_ids(department_id, date) if t not in taken]

    def book(self, request_id: str, slot_id: str, patient_ref: str) -> Booking:
        if not slots.is_scheduled(slot_id):
            raise SlotTaken(slot_id)
        dept, date, time = slots.parse_slot_id(slot_id)
        with db.connect() as conn:
            existing = db.find_appointment_by_key(conn, request_id)
            if existing is not None:
                return _booking(existing)
            patient = db.get_patient(conn, patient_ref)
            if patient is None:
                raise BookingNotFound(f"patient {patient_ref}")
            p = {"patient_name": patient["full_name"], "phone": patient["phone"], "patient_ref": patient_ref,
                 "slot_id": slot_id, "department_id": dept, "date": date, "time": time}
            try:
                db.insert_appointment(conn, db.new_appointment_id(), request_id, p)
            except sqlite3.IntegrityError as e:
                existing = db.find_appointment_by_key(conn, request_id)   # isi request ki doosri koshish jeet gayi
                if existing is not None:
                    return _booking(existing)
                raise SlotTaken(slot_id) from e
            return _booking(db.find_appointment_by_key(conn, request_id))

    def find_by_request(self, request_id: str) -> Booking | None:
        with db.connect() as conn:
            row = db.find_appointment_by_key(conn, request_id)
        return _booking(row) if row else None

    def list_for_patient(self, patient_ref: str) -> list[Booking]:
        with db.connect() as conn:
            return [_booking(row) for row in db.list_appointments_for_patient(conn, patient_ref)]

    def find_for_patient(self, patient_ref: str, reference: str) -> Booking | None:
        with db.connect() as conn:
            row = db.find_appointment_for_patient(conn, patient_ref, reference)
        return _booking(row) if row else None

    def cancel(self, reference: str, patient_ref: str) -> Booking:
        with db.connect() as conn:
            if not db.cancel_appointment(conn, reference, patient_ref):
                raise BookingNotFound(reference)
            return _booking(db.get_appointment(conn, reference))
