"""Hospital ke aam sawaal (FAQ): registration, documents, visiting hours wagairah."""

from hospital_agent.config import feature_required, load_hospital_info
from hospital_agent.text_match import contains_keyword


@feature_required("hospital_faq")
def get_hospital_info(question: str) -> dict:
    """Answers general hospital questions such as registration, documents to bring,
    visiting hours, pharmacy and emergency, from the hospital's approved FAQ.

    Args:
        question: The patient's question in Hindi or English.

    Returns:
        The matching answer with its source, or a message to contact the helpdesk.
    """
    info = load_hospital_info()
    best, best_hits = None, 0
    for topic in info.topics:
        hits = sum(1 for k in topic.keywords if contains_keyword(question, k))
        if hits > best_hits:
            best, best_hits = topic, hits
    if best is None:
        return {
            "status": "not_found",
            "message": "Is sawaal ki pakki jaankari mere paas nahin hai. Kripya hospital helpdesk se puchhein.",
            "helpdesk": info.helpdesk,
        }
    return {"status": "ok", "topic": best.id, "answer": best.answer, "source": best.source,
            "verified_on": best.verified_on.isoformat(), "hospital": info.hospital_name, "disclaimer": info.disclaimer}
