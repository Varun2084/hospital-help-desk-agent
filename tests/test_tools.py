import pytest

from hospital_agent.tools.appointments import check_available_slots
from hospital_agent.tools.departments import (
    get_department_info,
    list_departments,
    suggest_department,
)
from hospital_agent.tools.faq import get_hospital_info

TUESDAY = "2026-11-17"


def test_inactive_department_is_hidden():
    ids = [d["id"] for d in list_departments()["departments"]]
    assert "dental" not in ids
    assert get_department_info("dental")["status"] == "closed"


def test_unknown_department_lists_valid_ids():
    result = get_department_info("heart_dept")
    assert result["status"] == "error"
    assert "cardiology" in result["valid_ids"]


def test_symptoms_route_to_department_with_note():
    result = suggest_department("mere dil ki dhadkan tez hai")
    assert result["suggestions"][0]["id"] == "cardiology"
    assert "diagnosis nahin" in result["note"]


def test_keywords_match_whole_words_only():
    """Bug jo pakda gaya tha: 'heart' ke andar 'ear' milne se ENT bhi sujhaya ja raha tha."""
    ids = [s["id"] for s in suggest_department("I have a heart problem")["suggestions"]]
    assert ids == ["cardiology"]
    assert get_hospital_info("cardiology ka department kahan hai?")["status"] == "not_found"
    assert suggest_department("मुझे बुखार है")["suggestions"][0]["id"] == "general_medicine"


def test_unknown_symptoms_fall_back_to_general_medicine():
    assert suggest_department("kuch theek nahi lag raha")["suggestions"][0]["id"] == "general_medicine"


def test_missing_fallback_department_gives_helpdesk_not_crash(monkeypatch):
    """Review me mila: general_medicine config me na ho to tool crash ho jaata tha."""
    from hospital_agent.tools import departments
    monkeypatch.setattr(departments, "get_department", lambda _id: None)
    result = suggest_department("kuch theek nahi lag raha")
    assert result["suggestions"] == [] and "Helpdesk" in result["helpdesk"]


def test_no_opd_on_that_day():
    result = check_available_slots("cardiology", TUESDAY)
    assert result["status"] == "error" and "OPD Tue" in result["message"]


def test_past_date_is_rejected():
    assert check_available_slots("cardiology", "2026-11-09")["status"] == "error"


def test_faq_answers_with_source_and_date():
    result = get_hospital_info("registration kaise karein?")
    assert result["topic"] == "registration"
    assert result["verified_on"] and "Demo" in result["hospital"]


def test_unknown_question_points_to_helpdesk():
    result = get_hospital_info("canteen ka menu kya hai?")
    assert result["status"] == "not_found" and result["helpdesk"]



@pytest.mark.parametrize("question, topic", [
    ("रजिस्ट्रेशन कैसे करें?", "registration"),       # bug: Devanagari me likhe angrezi shabd nahin milte the
    ("कौन से डॉक्यूमेंट लाने हैं?", "documents"),
    ("एक्सरे कैसे कराएँ?", "radiology"),
    ("फार्मेसी कहाँ है?", "pharmacy"),
    ("registration kaise karein?", "registration"),
])
def test_faq_understands_devanagari_and_roman(question, topic):
    assert get_hospital_info(question)["topic"] == topic


@pytest.mark.parametrize("text, dept", [
    ("मुझे कार्डियोलॉजी में दिखाना है", "cardiology"),
    ("घुटने में फ्रैक्चर", "orthopaedics"),
    ("बच्चे को बुखार", "paediatrics"),
])
def test_departments_understand_devanagari(text, dept):
    ids = [s["id"] for s in suggest_department(text)["suggestions"]]
    assert dept in ids
