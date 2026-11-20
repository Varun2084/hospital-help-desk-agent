"""'Meri request ka kya hua?': login kiye patient ki requests aur notifications ki abhi ki sthiti.

Sthiti wahi jo staff ne pakki ki aur jo inbox me hai: model apni taraf se 'ho gaya' nahin kehta.
"""

from google.adk.tools import ToolContext

from hospital_agent import notifications, reception
from hospital_agent.config import feature_required
from hospital_agent.tools.appointments import _login_required
from hospital_agent.tools.common import current_patient

STATUS_WORDS = {"pending": "Review pending", "in_review": "Reception is reviewing", "resolved": "Resolved"}


@feature_required("appointments")
def my_updates(tool_context: ToolContext) -> dict:
    """Shows the LOGGED-IN patient's latest status updates: requests sent to reception and recent notifications.
    Use it for 'what happened to my request', 'meri request ka kya hua', 'any update?'.

    Returns:
        The requests with their current status and staff message, and the latest notifications.
    """
    patient = current_patient(tool_context)
    if patient is None:
        return _login_required()
    requests = [{"request_id": r["id"], "kind": r["kind"], "appointment_id": r["booking_ref"],
                 "requested": r["requested"], "status": STATUS_WORDS.get(r["status"], r["status"]),
                 "message": r["message"]} for r in reception.requests_for_patient(patient["id"])[:5]]
    inbox = notifications.inbox(patient["id"])["notifications"][:5]
    latest = [{"title": n["title"]["en"], "message": n["body"]["en"], "at": n["created_at"], "read": n["read"]}
              for n in inbox]
    return {"status": "ok", "requests": requests, "notifications": latest,
            "note": "Report only these statuses and messages. A request is done only if its status is Resolved. "
                    "For appointment, report or prescription details the patient opens the dashboard."}
