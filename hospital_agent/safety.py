"""Suraksha (safety) ke niyam: emergency pehchanna, phone number chhupana, aur tool calls ka audit log.

Dhyan rahe: shabdon ki list ek SAHAYAK jaanch hai, poori suraksha nahin. Isliye emergency number (112)
har jagah alag se bhi dikhaya jaata hai, aur asli hospital me yeh list staff se jaanchi jaani chahiye.
"""

import logging
import re

from google.adk.models import LlmResponse
from google.genai import types

logger = logging.getLogger("hospital_agent.audit")

EMERGENCY_LINE = "Emergency? Abhi 112 par call karein. / In an emergency call 112."

# PAKKE sanket: mile to turant emergency sandesh.
EMERGENCY_PATTERNS = [
    r"chest pain", r"(seene|chhati|chest) (me|mein) dard", r"heart attack", r"dil ka daura",
    r"(cannot|can ?not|can'?t|unable to|not able to) breathe", r"not breathing",
    r"(difficulty|trouble|problem) (in )?breathing", r"breathing (difficulty|problem|trouble)",
    r"shortness of breath", r"saans (nahi|nahin|nhi)", r"saans phool",
    r"saans (lene|aane) (me|mein) (takleef|dikkat|pareshani|mushkil)",
    r"unconscious", r"fainted", r"behosh", r"heavy bleeding", r"bleeding (heavily|a lot)",
    r"bahut khoon", r"khoon (beh|nikal)", r"zeher",
    r"(सीने|छाती) में दर्द", r"दिल का दौरा", r"(सांस|साँस) नहीं",
    r"(सांस|साँस) लेने में (तकलीफ|दिक्कत|परेशानी)", r"बेहोश", r"बहुत खून", r"(ज़हर|जहर)",
]
# KAMZOR sanket: purani baat ya follow-up ho to emergency nahin maante.
WEAK_PATTERNS = [r"accident", r"stroke", r"lakwa", r"seizure", r"poison", r"दुर्घटना", r"लकवा"]
ROUTINE_PATTERNS = [
    r"follow[- ]?up", r"puran[aie]", r"pichh?le", r"last (week|month|year)", r"history",
    r"(din|hafte|mahine|saal) pehle", r"(days?|weeks?|months?|years?) ago", r"ke baad", r"पिछले", r"पुरान",
]
SELF_HARM_PATTERNS = [r"suicide", r"kill myself", r"khudkushi", r"jeena nahi", r"marna chahta", r"आत्महत्या"]

# "no chest pain" ya "seene me dard nahi hai" jaise inkaar.
_NEGATION_BEFORE = re.compile(r"(?:\bno|\bwithout|\bnot having|\bdo(?:n'?t| not) have)\s+(?:any\s+)?$")
_NEGATION_AFTER = re.compile(r"^\s+(?:nahi|nahin|nhi|नहीं)\s+(?:hai|h|hain|है|हैं)(?:\s|$|[.,!?।])")

EMERGENCY_MESSAGE = (
    "Yeh emergency ho sakti hai. Abhi turant 112 par call karein ya sabse nazdeeki hospital ki "
    "Emergency me jaayein. Emergency ke liye appointment ki zaroorat nahin hoti.\n"
    "This may be an emergency. Call 112 now or go to the nearest hospital Emergency department."
)
SELF_HARM_MESSAGE = (
    "Aap jo mehsoos kar rahe hain, woh sunkar mujhe chinta hai. Aap akele nahin hain. "
    "Abhi Tele-MANAS helpline 14416 par baat karein (24x7, muft), ya khatra ho to 112 par call karein.\n"
    "You are not alone. Please call Tele-MANAS at 14416 (24x7, free), or 112 if you are in danger."
)

# Patient ne Hindi (देवनागरी) chuni ho to wahi tay sandesh Devanagari me.
EMERGENCY_MESSAGE_HI = (
    "यह इमरजेंसी हो सकती है। अभी तुरंत 112 पर कॉल करें या सबसे नज़दीकी अस्पताल की इमरजेंसी में जाएँ। "
    "इमरजेंसी के लिए अपॉइंटमेंट की ज़रूरत नहीं होती।"
)
SELF_HARM_MESSAGE_HI = (
    "आप जो महसूस कर रहे हैं, वह सुनकर मुझे चिंता है। आप अकेले नहीं हैं। अभी टेली-मानस हेल्पलाइन 14416 पर "
    "बात करें (24x7, मुफ़्त), या ख़तरा हो तो 112 पर कॉल करें।"
)
EMERGENCY_LINE_HI = "इमरजेंसी? अभी 112 पर कॉल करें।"
EMERGENCY_LINE_EN = "In an emergency, call 112 now."


def _found(pattern: str, text: str) -> bool:
    """Pattern mila aur uske aage-peechhe inkaar ('no ...', '... nahi hai') nahin hai."""
    for m in re.finditer(pattern, text):
        if _NEGATION_BEFORE.search(text[: m.start()]) or _NEGATION_AFTER.search(text[m.end():]):
            continue
        return True
    return False


def detect_risk(text: str) -> str | None:
    """Text me khatre ke sanket dhoondhta hai. Lautata hai 'self_harm', 'emergency' ya None."""
    lowered = text.lower()
    if any(re.search(p, lowered) for p in SELF_HARM_PATTERNS):
        return "self_harm"
    if any(_found(p, lowered) for p in EMERGENCY_PATTERNS):
        return "emergency"
    if any(_found(p, lowered) for p in WEAK_PATTERNS):
        routine = any(re.search(p, lowered) for p in ROUTINE_PATTERNS)
        return None if routine else "emergency"
    return None


def risk_message(risk: str, language: str | None = None) -> str:
    """Tay sandesh. language='Hindi' ho to Devanagari, warna Hindi+English dono."""
    if language == "Hindi":
        return SELF_HARM_MESSAGE_HI if risk == "self_harm" else EMERGENCY_MESSAGE_HI
    if language == "English":
        return (SELF_HARM_MESSAGE if risk == "self_harm" else EMERGENCY_MESSAGE).split("\n")[-1]
    return SELF_HARM_MESSAGE if risk == "self_harm" else EMERGENCY_MESSAGE


def _last_user_text(llm_request) -> str:
    for content in reversed(llm_request.contents or []):
        if content.role == "user" and content.parts:
            texts = [p.text for p in content.parts if p.text]
            if texts:
                return " ".join(texts)
    return ""


def emergency_guardrail(callback_context, llm_request) -> LlmResponse | None:
    """before_model_callback: khatra mile to model ki jagah tay sandesh lautata hai."""
    risk = detect_risk(_last_user_text(llm_request))
    if risk is None:
        return None
    logger.warning("event=guardrail outcome=%s", risk)
    state = getattr(callback_context, "state", None) or {}
    language = state.get("user:language")
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=risk_message(risk, language))]))


def mask_phone(phone: str) -> str:
    """9876543210 ko 98XXXXXX10 bana deta hai."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "XXXX"
    return digits[:2] + "X" * (len(digits) - 4) + digits[-2:]


def audit_tool_result(tool, args, tool_context, tool_response) -> dict | None:
    """after_tool_callback: har tool call ka sirf naam, nateeja aur request id log karta hai.
    Arguments (naam, phone) log me jaate hi nahin."""
    outcome = tool_response.get("status", "ok") if isinstance(tool_response, dict) else "ok"
    request_id = getattr(tool_context, "invocation_id", "-")
    logger.info("event=tool_call tool=%s outcome=%s request_id=%s", tool.name, outcome, request_id)
    return None
