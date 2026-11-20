"""Do kadam wale flow ka doosra kadam: patient ka Confirm button.

Pehla kadam (request_booking, request_cancellation, request_registration) model bulata hai, aur
sirf ek arzi (pending action) banti hai. Use pakka karna ya hatana MODEL KE HAATH ME NAHIN: yeh
functions web app ke Confirm / Discard button (aur terminal ke prompt) se seedha bulaye jaate hain.
"""

import hashlib
import json
from datetime import datetime

from hospital_agent import config, db, reschedule
from hospital_agent.tools import appointments, common, registration
from hospital_agent.tools.common import error

# Har kaam kis feature ka hai, aur use kaun poora karta hai.
HANDLERS = {
    "book": ("appointments", appointments.complete_booking),
    "cancel": ("appointments", appointments.complete_cancellation),
    "register": ("registration", registration.complete_registration),
    "reschedule": ("appointments", reschedule.complete_reschedule),
}


def fingerprint(payload_json: str) -> str:
    """Arzi ke exact details ki chhoti pehchaan. Card yahi wapas bhejta hai, taaki wahi arzi pakki ho jo dikhi thi."""
    return hashlib.sha256(payload_json.encode()).hexdigest()[:16]


def _load_own(conn, action_id: str, user_id: str, session_id: str):
    action = db.get_pending(conn, action_id.strip().upper())
    if action is None or action["user_id"] != user_id or action["session_id"] != session_id:
        return None
    return action


def confirm_pending(action_id: str, user_id: str, session_id: str, card_fingerprint: str | None = None,
                    patient_ref: str | None = None) -> dict:
    """Confirm button. Backend khud jaanchta hai: arzi isi patient aur baat-cheet ki hai, wahi hai jo card
    par dikhi (fingerprint), abhi pending hai aur samay ke andar hai. Phir HIS me slot ki taaza haalat dekh kar
    commit hota hai (complete_booking). Booking ya cancel ki arzi par button dabane wala wahi login kiya hua
    patient hona chahiye jiske naam par arzi bani (patient_ref)."""
    moment = common.now()
    with db.connect() as conn:
        action = _load_own(conn, action_id, user_id, session_id)
        if action is None:
            return error("Yeh request nahin mili. Kripya dobara shuru karein.")
        owner_patient = json.loads(action["payload"]).get("patient_ref")
        if owner_patient is not None and owner_patient != patient_ref:   # booking/cancel: wahi login chahiye
            return error("Yeh request nahin mili. Kripya login karke dobara shuru karein.")
        if card_fingerprint is not None and card_fingerprint != fingerprint(action["payload"]):
            return error("Card ki details badal gayi hain. Kripya naya request banayein.")
        # Pehle ho chuki? Wahi nateeja (button dobara dabane se doosri booking nahin).
        # 'committing' = HIS ko bheji thi par jawab nahin aaya: HIS se poochh kar aage badhenge.
        if action["status"] not in ("pending", "committing"):
            return json.loads(action["outcome"])
        if action["status"] == "pending" and moment > datetime.fromisoformat(action["expires_at"]):
            outcome = error("Confirm karne ka samay nikal gaya. Kripya dobara shuru karein.")
            db.fail_pending(conn, action["id"], outcome)
            return outcome
        feature, complete = HANDLERS[action["kind"]]
        if not config.load_features().get(feature, False):
            return error(f"'{feature}' feature abhi band hai.")
        return complete(conn, action["id"], json.loads(action["payload"]), moment)


def discard_pending(action_id: str, user_id: str, session_id: str) -> dict:
    """Discard button: sirf draft hatata hai. Pakki ho chuki appointment ka cancel alag workflow hai."""
    with db.connect() as conn:
        action = _load_own(conn, action_id, user_id, session_id)
        if action is None:
            return error("Yeh request nahin mili.")
        outcome = {"status": "discarded", "action_id": action["id"]}
        if not db.discard_pending(conn, action["id"], outcome):
            return json.loads(action["outcome"]) if action["outcome"] else error("Yeh request ab badli nahin ja sakti.")
        return outcome
