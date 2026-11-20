"""Chat se reschedule: model patient ki pasand samajhta hai, vikalp scheduler deta hai, badlaav patient ka button.

Dashboard ka Reschedule button bhi wahi workflow (hospital_agent/reschedule.py) bulata hai.
"""

from google.adk.tools import ToolContext

from hospital_agent import reschedule
from hospital_agent.config import feature_required
from hospital_agent.tools import common
from hospital_agent.tools.appointments import _login_required


@feature_required("appointments")
def reschedule_options(appointment_id: str, tool_context: ToolContext, date: str = "",
                       part_of_day: str = "any") -> dict:
    """Finds free slots the LOGGED-IN patient's upcoming appointment can move to. Read-only.
    First call my_appointments to know the patient's appointments; if two could match, ask which one.

    Args:
        appointment_id: The booking reference to move, for example 'HIS-APT-001'.
        date: Optional preferred date in YYYY-MM-DD (resolve 'Friday' with today_date first).
        part_of_day: 'morning', 'afternoon', 'evening' or 'any'.

    Returns:
        The current appointment and free alternatives with date, time and location, or an error.
    """
    patient = common.current_patient(tool_context)
    if patient is None:
        return _login_required()
    return reschedule.alternatives(patient["id"], appointment_id, date.strip(), part_of_day)


@feature_required("appointments")
def request_reschedule(appointment_id: str, new_date: str, new_time: str, tool_context: ToolContext) -> dict:
    """Prepares moving the LOGGED-IN patient's appointment to a free slot from reschedule_options.
    Nothing changes yet: the app shows the current and the new appointment, and the patient presses
    'Confirm change' or 'Keep current appointment'.

    Args:
        appointment_id: The booking reference to move.
        new_date: The new date in YYYY-MM-DD, from reschedule_options.
        new_time: The new time, for example '14:30', from reschedule_options.

    Returns:
        An action_id and the change preview, 'login_required', or an error.
    """
    patient = common.current_patient(tool_context)
    if patient is None:
        return _login_required()
    found = reschedule.alternatives(patient["id"], appointment_id, new_date.strip())
    if found.get("status") != "ok":
        return found
    slot = next((o for o in found["alternatives"] if o["time"] == new_time.strip()), None)
    if slot is None:
        return common.error(f"{new_date} {new_time} khaali nahin hai. reschedule_options se khaali samay dekhein.")
    user_id, session_id = common.owner(tool_context)
    return reschedule.create_preview(patient["id"], appointment_id, slot["slot_id"], user_id, session_id,
                                     tool_context.invocation_id)
