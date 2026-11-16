"""HIS (Hospital Information System) ka contract: agent ko slot aur booking ke liye kya chahiye.

Asli hospital me slot, booking aur booking reference HIS ke paas hote hain. Agent ka code sirf is
contract se baat karta hai, isliye local SQLite, sandbox ya asli vendor API badalne par tools nahin badalte.
"""

from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass
class Booking:
    reference: str          # HIS ka booking reference, jaise APT-1A2B3C ya HIS-000123
    patient_name: str
    phone: str
    department_id: str
    date: str               # YYYY-MM-DD
    time: str               # HH:MM
    status: str             # booked / cancelled

    def to_dict(self) -> dict:
        return asdict(self)


class HISError(Exception):
    """HIS se koi gadbad."""


class HISTimeout(HISError):
    """Jawab samay par nahin aaya. Kaam ho bhi sakta hai: idempotency key se dobara poochhein."""


class HISUnavailable(HISError):
    """HIS tak pahunch hi nahin paaye."""


class SlotTaken(HISError):
    """Yeh slot kisi aur ke naam ho chuka hai."""


class BookingNotFound(HISError):
    """Is reference (aur phone) se koi booking nahin."""


class HIS(Protocol):
    def booked_times(self, department_id: str, date: str) -> set[str]: ...

    def book(self, key: str, patient_name: str, phone: str, department_id: str, date: str,
             time: str) -> Booking:
        """Idempotent: wahi key dobara aaye to nayi booking nahin, wahi purani lautaye."""

    def find_by_key(self, key: str) -> Booking | None: ...

    def get_booking(self, reference: str) -> Booking | None: ...

    def cancel(self, reference: str, phone: str) -> Booking: ...
