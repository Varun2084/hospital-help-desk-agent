"""Demo: lab system ne ek report patient ke liye release ki (jaise LIS ka hook).

    python scripts/release_lab_report.py LAB-A-002

Report aur "nayi lab report" ka notification event ek hi transaction me save hote hain. Web app chal raha ho to
uska worker kuch second me patient ke bell tak pahuncha deta hai (ya: python -m hospital_agent.notifications --once).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from hospital_agent import db, records  # noqa: E402
from hospital_agent.records_pdf import make_pdf  # noqa: E402


def main() -> None:
    test_id = (sys.argv[1] if len(sys.argv) > 1 else "LAB-A-002").upper()
    with db.connect() as conn:
        row = db.get_lab_test(conn, test_id)
    if row is None:
        sys.exit(f"{test_id} nahin mila. Pehle: python scripts/seed_demo_patients.py")
    pdf = make_pdf(f"Laboratory report: {row['test_name']}", [
        f"Patient: {row['patient_ref']}", "Sample: synthetic", "", "Result: synthetic demo values",
        "", "Values are synthetic demo data. Your doctor explains real reports."])
    if records.release_lab_report(test_id, pdf):
        print(f"{test_id} released. Notification event outbox me: lab.report_released:{test_id}")
    else:
        print(f"{test_id} pehle se released hai. Naya notification nahin bana.")


if __name__ == "__main__":
    main()
