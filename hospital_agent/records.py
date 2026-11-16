"""Patient ke health records: lab tests aur prescriptions. Har function login kiye patient (patient_ref) tak simit.

Lab test ki do alag cheezein hain: progress (status) aur report. Status har stage par dikhta hai
(Ordered -> Sample collected -> Processing -> Report available). Report sirf tab milti hai jab source system
use patient ke liye release kare. Documents hospital ke original PDF hain: model inhe na banata hai na badalta hai.
"""

from hospital_agent import db
from hospital_agent.config import get_department

LAB_STEPS = ["ordered", "sample_collected", "processing", "report_available"]


def _department(department_id: str | None) -> str:
    dept = get_department(department_id) if department_id else None
    return dept.name if dept else (department_id or "")


def lab_tests_for(patient_ref: str) -> list[dict]:
    with db.connect() as conn:
        rows = db.list_lab_tests(conn, patient_ref)
    return [{"test_id": r["id"], "test_name": r["test_name"], "ordered_on": r["ordered_on"],
             "department": _department(r["department_id"]), "status": r["status"],
             "step": LAB_STEPS.index(r["status"]) + 1 if r["status"] in LAB_STEPS else 0, "steps": len(LAB_STEPS),
             "report_available": bool(r["report_released"]) and r["status"] == "report_available"}
            for r in rows]


def lab_report_pdf(patient_ref: str, test_id: str) -> bytes | None:
    """Apna aur released ho to PDF; warna None (anjaan, doosre ka, ya abhi release nahin: ek hi jawab)."""
    with db.connect() as conn:
        row = db.get_lab_report(conn, patient_ref, test_id.upper())
    return bytes(row["report_pdf"]) if row else None


def prescriptions_for(patient_ref: str) -> list[dict]:
    with db.connect() as conn:
        rows = db.list_prescriptions(conn, patient_ref)
    return [{"prescription_id": r["id"], "visit_ref": r["visit_ref"], "visit_date": r["visit_date"],
             "department": _department(r["department_id"]), "doctor": r["doctor"]} for r in rows]


def prescription_pdf(patient_ref: str, prescription_id: str) -> bytes | None:
    with db.connect() as conn:
        row = db.get_prescription(conn, patient_ref, prescription_id.upper())
    return bytes(row["document_pdf"]) if row else None
