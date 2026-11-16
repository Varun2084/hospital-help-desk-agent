"""Confirm card: model ki arzi ko patient ke saamne button ke roop me rakhna, aur button ka nateeja
baat-cheet me wapas likhna, taaki agent ko pata rahe ki kya hua. Web app aur terminal dono yahi istemaal karte hain."""

from google.adk.events import Event
from google.genai import types

DESK_FOR_KIND = {"book": "appointment_desk", "cancel": "appointment_desk", "register": "registration_desk"}
CARD_FIELDS = ("action_id", "kind", "summary", "expires_at", "fingerprint")


def cards_from_event(event) -> list[dict]:
    """Event me kisi tool ne 'needs_confirmation' lautaya ho to uska card."""
    cards = []
    for part in (event.content.parts if event.content else None) or []:
        response = part.function_response.response if part.function_response else None
        if isinstance(response, dict) and response.get("status") == "needs_confirmation":
            cards.append({k: response.get(k) for k in CARD_FIELDS})
        elif isinstance(response, dict) and response.get("status") == "login_required":
            cards.append({"kind": "login", "summary": response.get("preview") or {}})   # login maangne wala card
    return cards


def outcome_note(kind: str, button: str, result: dict) -> str:
    """Agent ke liye ek line: patient ne kaun sa button dabaya aur kya hua."""
    status = result.get("status")
    detail = ", ".join(f"{k}={result[k]}" for k in ("appointment_id", "patient_id", "date", "time") if k in result)
    if status == "error":
        detail = result.get("message", "")
    return f"[App] Patient pressed {button} on the {kind} card. Result: {status}. {detail}".strip()


async def record_outcome(session_service, session, kind: str, button: str, result: dict) -> None:
    text = outcome_note(kind, button, result)
    event = Event(author=DESK_FOR_KIND.get(kind, "reception"),
                  content=types.Content(role="model", parts=[types.Part(text=text)]))
    await session_service.append_event(session, event)
