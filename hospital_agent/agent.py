"""Agents banana: ek reception (coordinator) aur har chalu feature ke liye ek specialist."""

import os

from google.adk.agents import Agent
from google.adk.tools import ToolContext

from hospital_agent.config import load_features
from hospital_agent.safety import audit_tool_result, emergency_guardrail
from hospital_agent.tools import FEATURE_TOOLS

MODEL = os.environ.get("HOSPITAL_MODEL", "gemini-3.5-flash-lite")

COMMON_RULES = (
    "Rules: You are a hospital help desk assistant, not a doctor. Never diagnose, never suggest "
    "medicines or doses. If symptoms sound serious, tell the patient to go to Emergency or call 112. "
    "Reply in the patient's language (Hindi or English); a saved preference is: '{user:language?}'. "
    "Use only facts returned by your tools; if a tool has no answer, say so."
)

SPECIALISTS = {
    "department_guide": {
        "name": "department_guide",
        "description": "Answers which departments exist, where they are, their OPD days and hours, "
                       "and which department fits the patient's symptoms.",
        "instruction": "You help patients find the right department. Use list_departments, "
                       "get_department_info and suggest_department. When suggesting a department, "
                       "always repeat the tool's note that this is not a diagnosis. ",
    },
    "appointments": {
        "name": "appointment_desk",
        "description": "Checks free OPD slots, books appointments and cancels them.",
        "instruction": "You book and cancel OPD appointments. Steps: call today_date to resolve "
                       "dates, call check_available_slots, collect the patient's name and 10-digit "
                       "mobile number, then call request_booking (or request_cancellation). Read the "
                       "returned summary to the patient exactly and ask for a clear yes or no. Only "
                       "after the patient replies yes in their next message, call confirm_action with "
                       "the action_id. Never say a booking or cancellation is done unless "
                       "confirm_action returned 'booked' or 'cancelled'. Never invent a slot. ",
    },
    "hospital_faq": {
        "name": "info_desk",
        "description": "Answers general questions: registration, documents to bring, visiting hours, "
                       "pharmacy and emergency.",
        "instruction": "You answer general hospital questions using get_hospital_info only, and "
                       "mention the disclaimer the tool returns. ",
    },
    "lab_reports": {
        "name": "lab_desk",
        "description": "Tells patients whether their lab report is ready and where to collect it.",
        "instruction": "You check lab report status with get_lab_report_status. Ask for the report id "
                       "and mobile number. Never interpret or discuss test results; the doctor will. ",
    },
}


def save_language_preference(language: str, tool_context: ToolContext) -> dict:
    """Saves the patient's preferred reply language for this and future conversations.

    Args:
        language: 'Hindi' or 'English'.
    """
    if language not in ("Hindi", "English"):
        return {"status": "error", "message": "Sirf 'Hindi' ya 'English' chalega."}
    tool_context.state["user:language"] = language
    return {"status": "saved", "language": language}


def build_specialist(feature: str) -> Agent:
    spec = SPECIALISTS[feature]
    return Agent(
        name=spec["name"],
        model=MODEL,
        description=spec["description"],
        instruction=spec["instruction"] + COMMON_RULES,
        tools=FEATURE_TOOLS[feature],
        before_model_callback=emergency_guardrail,
        after_tool_callback=audit_tool_result,
    )


def build_root_agent(features: dict[str, bool] | None = None) -> Agent:
    features = features if features is not None else load_features()
    enabled = [f for f, on in features.items() if on and f in SPECIALISTS]
    specialists = [build_specialist(f) for f in enabled]
    return Agent(
        name="reception",
        model=MODEL,
        description="Hospital reception that greets patients and routes them to the right desk.",
        instruction=(
            "You are the reception of Demo Public Hospital, New Delhi (a fictional demo hospital). "
            "Greet the patient briefly, "
            "understand what they need and transfer them to the right specialist agent. If the "
            "patient asks to reply in Hindi or English, call save_language_preference. "
            "If no specialist fits, say what you can help with. " + COMMON_RULES
        ),
        tools=[save_language_preference],
        sub_agents=specialists,
        before_model_callback=emergency_guardrail,
    )


root_agent = build_root_agent()
