"""Slot ki pehchaan (slot_id) aur department ke schedule se slot banana.

slot_id ek schedule entry hai: kaun sa department, kis din, kis samay. Jaise
    SLOT-cardiology-20261123-0900
Do patient ek hi slot_id chun sakte hain; unki booking request ki id (request_id) alag hoti hai.

Asli HIS apna roster aur slot_id khud deta hai. Yahan LocalHIS aur sandbox dono isi file se,
hospital config ke OPD samay ke hisaab se, slot banate hain.
"""

import re
from datetime import date as Date

from hospital_agent.config import get_department

SLOT_ID_PATTERN = re.compile(r"^SLOT-([a-z][a-z0-9_]*)-(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})$")


def _to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def schedule_times(opd_hours: str, slot_minutes: int) -> list[str]:
    """'09:00-12:00' aur 30 minute -> ['09:00', '09:30', ...]. Aakhri slot OPD band hone se pehle khatam."""
    start_s, end_s = opd_hours.split("-")
    current, end = _to_minutes(start_s), _to_minutes(end_s)
    times = []
    while current + slot_minutes <= end:
        times.append(f"{current // 60:02d}:{current % 60:02d}")
        current += slot_minutes
    return times


def make_slot_id(department_id: str, date: str, time: str) -> str:
    return f"SLOT-{department_id}-{date.replace('-', '')}-{time.replace(':', '')}"


def parse_slot_id(slot_id: str) -> tuple[str, str, str] | None:
    """slot_id -> (department_id, 'YYYY-MM-DD', 'HH:MM'), ya galat ho to None."""
    m = SLOT_ID_PATTERN.fullmatch(slot_id or "")
    if not m:
        return None
    dept, y, mo, d, h, mi = m.groups()
    return dept, f"{y}-{mo}-{d}", f"{h}:{mi}"


def scheduled_slot_ids(department_id: str, date: str) -> list[tuple[str, str]]:
    """Us din ke saare slot (booked ho ya khaali): [(slot_id, time), ...]. OPD band ho to khaali list."""
    dept = get_department(department_id)
    if dept is None or not dept.active:
        return []
    if Date.fromisoformat(date).strftime("%a") not in dept.opd_days:
        return []
    return [(make_slot_id(department_id, date, t), t) for t in schedule_times(dept.opd_hours, dept.slot_minutes)]


def is_scheduled(slot_id: str) -> bool:
    parsed = parse_slot_id(slot_id)
    if parsed is None:
        return False
    dept, date, _ = parsed
    return any(sid == slot_id for sid, _ in scheduled_slot_ids(dept, date))
