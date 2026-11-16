"""Health records ke liye chat ka kaam sirf raasta dikhana hai.

"Meri reports kahan hain?" par yeh tool dashboard ka sahi tab kholne ka button deta hai. Report ki values,
dawai ke naam ya dose model kabhi nahin padhta ya likhta: patient dashboard par hospital ka original document
dekhta hai, jo login aur maalik ki jaanch ke baad hi milta hai.
"""

from hospital_agent.config import feature_required

SECTIONS = {"lab_tests", "prescriptions", "appointments"}


@feature_required("health_records")
def open_my_records(section: str) -> dict:
    """Offers a button that opens the patient's own dashboard at a section. It never reads the records.

    Args:
        section: 'lab_tests' for lab tests and reports, 'prescriptions', or 'appointments'.

    Returns:
        An instruction for the app to show an 'open dashboard' button.
    """
    section = section.strip().lower()
    if section not in SECTIONS:
        return {"status": "error", "message": "section: lab_tests, prescriptions ya appointments."}
    return {"status": "open_dashboard", "section": section,
            "note": "The app shows a button. The dashboard asks for login if needed. Do not describe any "
                    "report values, medicines or doses."}
