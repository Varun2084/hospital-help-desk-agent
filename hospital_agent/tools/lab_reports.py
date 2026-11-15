"""Naya feature ka udaharan: lab report ka status batana.

DEMO: yahan reports ek dictionary me hain. Asli hospital me yeh tool Lab Information System
ke API se (ya ek MCP server ke through) judega; tool ka naam aur jawab ka dhaancha wahi rahega.
"""

from hospital_agent.config import feature_required

DEMO_REPORTS = {
    "LAB-1001": {"phone": "9876543210", "test": "Complete Blood Count", "status": "ready",
                 "collect_from": "Lab counter 3, Main OPD Block"},
    "LAB-1002": {"phone": "9123456789", "test": "Lipid Profile", "status": "processing",
                 "expected": "2 working days"},
}


@feature_required("lab_reports")
def get_lab_report_status(report_id: str, phone: str) -> dict:
    """Tells whether a lab report is ready. It never shares the test results themselves.

    Args:
        report_id: The id printed on the lab receipt, for example 'LAB-1001'.
        phone: The 10-digit mobile number given at sample collection.

    Returns:
        The report status and where to collect it, or an error.
    """
    report = DEMO_REPORTS.get(report_id.strip().upper())
    if report is None or report["phone"] != phone:
        return {"status": "error", "message": "Is report ID aur phone number se koi report nahin mili."}
    # Jawab me sirf status. Test ka naam ya phone nahin: test ka naam bhi sehat ki jaankari hai.
    result = {"status": "ok", "report_id": report_id.strip().upper(), "report_status": report["status"]}
    if report["status"] == "ready":
        result["collect_from"] = report["collect_from"]
    else:
        result["expected"] = report["expected"]
    return result
