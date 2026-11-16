"""Agents banana: ek reception (coordinator) aur har chalu feature ke liye ek specialist."""

import os

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.tools import ToolContext

from hospital_agent.config import load_features, load_hospital_info
from hospital_agent.safety import audit_tool_result, emergency_guardrail
from hospital_agent.tools import FEATURE_TOOLS

MODEL = os.environ.get("HOSPITAL_MODEL", "gemini-3.5-flash-lite")

COMMON_RULES = (
    "Rules: You are a hospital help desk assistant, not a doctor. Never diagnose, never suggest "
    "medicines or doses. If symptoms sound serious, tell the patient to go to Emergency or call 112. "
    "Language: the patient's chosen language is '{user:language?}'. If it is Hindi, reply ONLY in "
    "Hindi written in Devanagari script (no Roman/Hinglish), even if the patient types in Roman or "
    "English, and translate tool messages into Devanagari Hindi. If it is English, reply ONLY in "
    "English and translate tool messages into English. Keep appointment IDs, times, dates, phone "
    "numbers and department ids exactly as the tools return them. If no language is chosen, reply "
    "in the patient's language. "
    "Use only facts returned by your tools; if a tool has no answer, say so."
)

SPECIALISTS = {
    "department_guide": {
        "name": "department_guide",
        "description": "Answers which departments exist, where they are, their OPD days and hours, "
                       "and which department fits the patient's symptoms.",
        "instruction": "You help patients find the right department. Use list_departments, "
                       "get_department_info and suggest_department. Pass symptoms to suggest_department in "
                       "the patient's words AND in simple English (for example 'सीने में दर्द chest pain'). "
                       "When suggesting a department, "
                       "always repeat the tool's note that this is not a diagnosis. ",
    },
    "appointments": {
        "name": "appointment_desk",
        "description": "Checks free OPD slots, books appointments and cancels them.",
        "instruction": "You book and cancel OPD appointments for REGISTERED patients. Steps: call today_date "
                       "to resolve dates, call check_available_slots, collect the patient's name and 10-digit "
                       "mobile number as given at registration, then call request_booking (or "
                       "request_cancellation). If request_booking returns 'not_registered', explain that "
                       "registration comes first and transfer to registration_desk; do not book. The app then "
                       "shows the patient a card with the exact details and two buttons, Confirm and "
                       "Discard. Tell the patient to check the card and press a button. You cannot confirm "
                       "it yourself, and a typed 'yes' or 'ok' does not confirm it. Never say a booking or "
                       "cancellation is done unless the app has reported the result in this conversation. "
                       "If the app reports 'in_progress', say the hospital system did not answer in time, "
                       "the app is checking the booking status, nothing is lost, and the patient can press "
                       "'Check status'. If the app reports the slot was taken, ask the patient to pick one of "
                       "the new times shown on the card. Never invent a slot. ",
    },
    "hospital_faq": {
        "name": "info_desk",
        "description": "Answers general questions: registration, documents to bring, visiting hours, "
                       "pharmacy, emergency, and tests or scans such as X-ray, ultrasound, CT, MRI "
                       "and blood tests (these are not departments).",
        "instruction": "You answer general hospital questions using get_hospital_info only, and "
                       "mention the disclaimer the tool returns. Call get_hospital_info with the patient's "
                       "words AND a short English topic word, for example 'रजिस्ट्रेशन कैसे करें "
                       "registration'. If it returns not_found, give the helpdesk location it returns. ",
    },
    "registration": {
        "name": "registration_desk",
        "description": "Registers a new patient and gives a patient ID. Use this when the patient "
                       "wants to register, get a new patient ID or a registration card.",
        "instruction": "You register new patients. Ask, one or two at a time, for: full name, age, "
                       "gender, 10-digit mobile number and town or village with district. If the patient "
                       "is under 18, also ask for the parent or guardian's name. Never ask for Aadhaar, "
                       "medical history, symptoms or medicines. Call request_registration and read the "
                       "consent note to the patient. The app shows a card with Confirm and Discard buttons; "
                       "you cannot confirm it yourself. Never say registration is done unless the app has "
                       "reported 'registered'. If the tool says already_registered, do not register again: give that "
                       "patient ID. Tell the patient this is a demo ID. After registration, if the patient "
                       "wants an appointment, transfer to appointment_desk. ",
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


def hospital_name() -> str:
    """Hospital ka naam hamesha config se, taaki har profile (demo, Rewa) apna hi naam bole."""
    return load_hospital_info().hospital_name


def build_specialist(feature: str) -> Agent:
    spec = SPECIALISTS[feature]
    return Agent(
        name=spec["name"],
        model=MODEL,
        description=spec["description"],
        instruction=f"You work at {hospital_name()}. " + spec["instruction"] + COMMON_RULES,
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
            f"You are the reception of {hospital_name()}. "
            "If the chosen language is empty, your FIRST reply must only ask the patient to pick a "
            "language: '1. हिंदी (देवनागरी)  2. English', and when they answer, call "
            "save_language_preference with 'Hindi' or 'English'. Then greet the patient briefly, "
            "understand what they need and transfer them to the right specialist agent. If the "
            "patient later asks to switch language, call save_language_preference again. "
            "If no specialist fits, say what you can help with. " + COMMON_RULES
        ),
        tools=[save_language_preference],
        sub_agents=specialists,
        before_model_callback=emergency_guardrail,
    )


root_agent = build_root_agent()

# 'adk web' aur run_demo.py dono isi App ko chalate hain. Naam folder ke naam jaisa hona chahiye.
app = App(name="hospital_agent", root_agent=root_agent)
