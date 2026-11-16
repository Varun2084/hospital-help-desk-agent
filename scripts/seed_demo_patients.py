"""Do synthetic patient (A aur B), har ek ki ek Cardiology booking. Lesson 4 ke login demo ke liye.

    python scripts/seed_demo_patients.py

Dobara chalane par kuch dohraya nahin jaata (patients wahi, bookings wahi request_id se).
HIS_MODE=sandbox ho to bookings Fake HIS me jaati hain (pehle python -m his_sandbox chalayein).
Login: Patient ID + phone, phir screen par dikhne wala demo code.
"""

import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from hospital_agent import db, his  # noqa: E402
from hospital_agent.config import get_department  # noqa: E402
from hospital_agent.his import slots  # noqa: E402
from hospital_agent.tools import common  # noqa: E402

DEMO_PATIENTS = [  # (patient ID, naam, phone, booking ka samay)
    ("DEMO-PATIENT-A", "Demo Patient A", "9000000011", "09:00"),
    ("DEMO-PATIENT-B", "Demo Patient B", "9000000012", "09:30"),
]


def next_opd_day(department_id: str = "cardiology") -> str:
    dept = get_department(department_id)
    day = common.today() + timedelta(days=1)
    while day.strftime("%a") not in dept.opd_days:
        day += timedelta(days=1)
    return day.isoformat()


def seed() -> dict:
    """Patients + ek-ek booking. {patient_id: booking_ref} lautata hai."""
    date = next_opd_day()
    refs = {}
    with db.connect() as conn, conn:
        for pid, name, phone, _ in DEMO_PATIENTS:
            if db.get_patient(conn, pid) is None:
                conn.execute("INSERT INTO patients (id, full_name, age, gender, phone, city, guardian_name, "
                             "created_at) VALUES (?, ?, 35, 'Other', ?, 'Rewa', NULL, ?)",
                             (pid, name, phone, db.now_text()))
    system = his.get_his()
    for pid, _, _, time in DEMO_PATIENTS:
        request_id = f"SEED-{pid}"
        booking = system.find_by_request(request_id)
        if booking is None:
            try:
                booking = system.book(request_id, slots.make_slot_id("cardiology", date, time), pid)
            except his.SlotTaken:   # yeh samay pehle se kisi ka: pehla khaali slot
                booking = system.book(request_id, system.open_slots("cardiology", date)[0].slot_id, pid)
        refs[pid] = booking.reference
    return refs


if __name__ == "__main__":
    for (pid, name, phone, _), ref in zip(DEMO_PATIENTS, seed().values(), strict=True):
        print(f"{name:<15} Patient ID {pid:<15} phone {phone}   Cardiology booking {ref}")
    print("\nLogin: Patient ID + phone -> screen par demo code. Patient B ka reference Patient A ke login me 404 dega.")
