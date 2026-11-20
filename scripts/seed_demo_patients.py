"""Do synthetic patient (A aur B): ek-ek aane wali Cardiology booking, ek pichhli visit, aur health records.

Lesson 4 (login, My Appointments) aur Lesson 5 (dashboard, lab tests, prescriptions) ke demo ke liye:
    Patient A: ek lab test 'processing', ek released report, ek issued prescription
    Patient B: alag released report aur alag prescription

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
from hospital_agent.records_pdf import make_pdf  # noqa: E402
from hospital_agent.tools import common  # noqa: E402

DEMO_STAFF = [  # (staff ID, naam, phone): Reception desk (/staff) ke liye
    ("STAFF-RECEPTION-1", "Demo Receptionist 1", "9000000021"),
    ("STAFF-RECEPTION-2", "Demo Receptionist 2", "9000000022"),
]

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


def _report(patient: str, pid: str, test: str, lines: list[str]) -> bytes:
    return make_pdf(f"Laboratory report: {test}", [f"Patient: {patient} ({pid})", "Sample: synthetic", ""] + lines
                    + ["", "Values are synthetic demo data. Your doctor explains real reports."])


def _prescription(patient: str, pid: str, visit: str, date: str, doctor: str) -> bytes:
    return make_pdf("OPD prescription (Cardiology)", [
        f"Patient: {patient} ({pid})", f"Visit: {visit}   Date: {date}", f"Doctor: {doctor}", "",
        "Rx (synthetic placeholders, not real medicines):", "  1. Medicine-A  - as written by the doctor",
        "  2. Medicine-B  - as written by the doctor", "", "Follow-up: as advised in OPD"])


def seed_records(past_day: str) -> None:
    """Lab tests aur prescriptions (synthetic). Dobara chalane par wahi rows (INSERT OR REPLACE)."""
    a, b = "Demo Patient A", "Demo Patient B"
    with db.connect() as conn:
        db.save_lab_test(conn, {"id": "LAB-A-001", "patient_ref": "DEMO-PATIENT-A", "visit_ref": "VISIT-A-001",
                                "test_name": "Complete Blood Count (CBC)", "department_id": "cardiology",
                                "ordered_on": past_day, "status": "report_available", "report_released": 1,
                                "report_pdf": _report(a, "DEMO-PATIENT-A", "Complete Blood Count (CBC)", [
                                    "Haemoglobin        13.8 g/dL     (13.0 - 17.0)",
                                    "WBC count          7,200 /uL     (4,000 - 11,000)",
                                    "Platelets          2.6 lakh/uL   (1.5 - 4.5)"])})
        db.save_lab_test(conn, {"id": "LAB-A-002", "patient_ref": "DEMO-PATIENT-A", "visit_ref": "VISIT-A-001",
                                "test_name": "Lipid Profile", "department_id": "cardiology", "ordered_on": past_day,
                                "status": "processing", "report_released": 0, "report_pdf": None})
        db.save_lab_test(conn, {"id": "LAB-B-001", "patient_ref": "DEMO-PATIENT-B", "visit_ref": "VISIT-B-001",
                                "test_name": "Thyroid Profile (TSH)", "department_id": "cardiology",
                                "ordered_on": past_day, "status": "report_available", "report_released": 1,
                                "report_pdf": _report(b, "DEMO-PATIENT-B", "Thyroid Profile (TSH)", [
                                    "TSH                2.1 uIU/mL    (0.4 - 4.0)"])})
        db.save_prescription(conn, {"id": "RX-A-001", "patient_ref": "DEMO-PATIENT-A", "visit_ref": "VISIT-A-001",
                                    "visit_date": past_day, "department_id": "cardiology",
                                    "doctor": "Dr. Demo Cardiologist", "issued": 1,
                                    "document_pdf": _prescription(a, "DEMO-PATIENT-A", "VISIT-A-001", past_day,
                                                                  "Dr. Demo Cardiologist")})
        db.save_prescription(conn, {"id": "RX-B-001", "patient_ref": "DEMO-PATIENT-B", "visit_ref": "VISIT-B-001",
                                    "visit_date": past_day, "department_id": "cardiology",
                                    "doctor": "Dr. Demo Physician", "issued": 1,
                                    "document_pdf": _prescription(b, "DEMO-PATIENT-B", "VISIT-B-001", past_day,
                                                                  "Dr. Demo Physician")})


def past_opd_day(department_id: str = "cardiology") -> str:
    dept = get_department(department_id)
    day = common.today() - timedelta(days=7)
    while day.strftime("%a") not in dept.opd_days:
        day -= timedelta(days=1)
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
    with db.connect() as conn:
        for sid, name, phone in DEMO_STAFF:
            db.save_staff(conn, sid, name, phone)
    system = his.get_his()
    past = past_opd_day()
    seed_records(past)
    for pid, _, _, time in DEMO_PATIENTS:   # pichhli visit (Appointments tab me 'past')
        if system.find_by_request(f"VISIT-{pid}") is None:
            system.book(f"VISIT-{pid}", slots.make_slot_id("cardiology", past, time), pid)
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
    print("Records: A -> LAB-A-001 (report), LAB-A-002 (processing), RX-A-001;  B -> LAB-B-001, RX-B-001")
    print("Staff (Reception desk: http://127.0.0.1:8000/staff): "
          + ", ".join(f"{sid} / {phone}" for sid, _, phone in DEMO_STAFF))
    print("\nLogin: Patient ID + phone -> screen par demo code. Patient B ka reference Patient A ke login me 404 dega.")
