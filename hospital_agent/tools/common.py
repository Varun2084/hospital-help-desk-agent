"""Tools ki saajhi cheezein: Bharat ka samay, error ka roop, phone ka niyam aur 'arzi' (pending action) banana."""

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from google.adk.tools import ToolContext

from hospital_agent import db

IST = ZoneInfo("Asia/Kolkata")
PHONE_PATTERN = re.compile(r"^[6-9]\d{9}$")
CONFIRM_WINDOW_MINUTES = 10


def now() -> datetime:
    """Abhi ka samay, IST me. Tests ise patch karke koi bhi pal bana lete hain."""
    return datetime.now(IST)


def today() -> date:
    return now().date()


def error(message: str) -> dict:
    return {"status": "error", "message": message}


def owner(tool_context: ToolContext) -> tuple[str, str]:
    """Arzi kis patient aur kis baat-cheet ki hai. Yeh ADK bharta hai, model nahin."""
    return tool_context.user_id, tool_context.session.id


def create_pending_action(kind: str, payload: dict, summary: dict, tool_context: ToolContext) -> dict:
    """Database me sirf arzi likhta hai. Asli kaam patient ke Confirm button ke baad hoga."""
    user_id, session_id = owner(tool_context)
    expires_at = (now() + timedelta(minutes=CONFIRM_WINDOW_MINUTES)).isoformat(timespec="seconds")
    with db.connect() as conn:
        action_id = db.create_pending(conn, kind, payload, user_id, session_id,
                                      tool_context.invocation_id, expires_at)
    return {
        "status": "needs_confirmation",
        "action_id": action_id,
        "kind": kind,
        "summary": summary,
        "expires_at": expires_at,
        "fingerprint": hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()[:16],
        "next_step": "The app now shows the patient a card with these details and two buttons: Confirm and "
                     "Discard. Ask them to check the card and press a button. You cannot confirm it yourself; "
                     "never say it is done until the app reports the result.",
    }
