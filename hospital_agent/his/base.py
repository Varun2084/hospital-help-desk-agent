"""HIS (Hospital Information System) ka contract: agent ko slot aur booking ke liye kya chahiye.

Asli hospital me slot, booking aur booking reference HIS ke paas hote hain. Agent ka code sirf is
contract se baat karta hai, isliye local SQLite, sandbox ya asli vendor API badalne par tools nahin badalte.

Teen alag pehchaan:
    slot_id     ek schedule entry (department, din, samay). Do patient ek hi slot_id chun sakte hain.
    patient_ref registered patient ki ID (yahan DEMO-..., asli hospital me UHID).
    request_id  ek booking attempt. Wahi attempt dobara bheja jaaye (retry) to wahi request_id jaati hai.
"""

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass
class Slot:
    slot_id: str
    time: str               # HH:MM


@dataclass
class Booking:
    reference: str          # HIS ka booking reference, jaise APT-1A2B3C ya HIS-APT-000123
    slot_id: str
    patient_ref: str
    department_id: str
    date: str               # YYYY-MM-DD
    time: str               # HH:MM
    status: str             # confirmed / cancelled

    def to_dict(self) -> dict:
        return asdict(self)


class HISError(Exception):
    """HIS se koi gadbad."""


class HISTimeout(HISError):
    """Jawab samay par nahin aaya. Kaam ho bhi sakta hai: request_id se dobara poochhein."""


class HISUnavailable(HISError):
    """HIS tak pahunch hi nahin paaye."""


class SlotTaken(HISError):
    """Yeh slot kisi aur ke naam ho chuka hai (ya schedule me hai hi nahin)."""


class BookingNotFound(HISError):
    """Is reference (aur patient) se koi booking nahin."""


class HIS(Protocol):
    def open_slots(self, department_id: str, date: str) -> list[Slot]:
        """Us din ke khaali slot, slot_id ke saath. 'Abhi ke baad' wali jaanch agent karta hai."""

    def book(self, request_id: str, slot_id: str, patient_ref: str) -> Booking:
        """Idempotent: wahi request_id dobara aaye to nayi booking nahin, wahi purani lautaye."""

    def find_by_request(self, request_id: str) -> Booking | None: ...

    def list_for_patient(self, patient_ref: str) -> list[Booking]:
        """Sirf is patient ki bookings."""

    def find_for_patient(self, patient_ref: str, reference: str) -> Booking | None:
        """Reference se booking, par sirf tab jab woh isi patient ki ho. Doosre ki ho to None (jaise mili hi nahin)."""

    def cancel(self, reference: str, patient_ref: str) -> Booking: ...
