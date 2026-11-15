import inspect
import logging
from types import SimpleNamespace

import pytest
from google.adk.models import LlmRequest
from google.genai import types

from hospital_agent.agent import build_root_agent
from hospital_agent.safety import audit_tool_result, detect_risk, emergency_guardrail, mask_phone
from hospital_agent.tools import FEATURE_TOOLS


def _request(text: str) -> LlmRequest:
    return LlmRequest(contents=[types.Content(role="user", parts=[types.Part(text=text)])])


def test_detect_risk():
    assert detect_risk("Papa ko seene me dard ho raha hai") == "emergency"
    assert detect_risk("I want to kill myself") == "self_harm"
    assert detect_risk("Cardiology OPD kab hai?") is None


@pytest.mark.parametrize("text", [
    "I cannot breathe", "I can't breathe", "mujhe saans lene me takleef hai", "saans nahi aa rahi",
    "मुझे सांस लेने में तकलीफ है", "papa ko heart attack aaya hai", "abhi accident hua hai",
    "no fever but chest pain since morning", "bahut khoon beh raha hai",
])
def test_emergency_phrases_in_three_languages(text):
    assert detect_risk(text) == "emergency"


@pytest.mark.parametrize("text", [
    "accident follow-up appointment chahiye", "pichhle saal stroke hua tha, neurology OPD kab hai?",
    "no chest pain, just a routine checkup", "seene me dard nahi hai, bas BP check karana hai",
    "Orthopaedics ki OPD kab hai?",
])
def test_routine_messages_are_not_blocked(text):
    """Review me mila: 'accident follow-up appointment' ko emergency maan kar booking rok di jaati thi."""
    assert detect_risk(text) is None


def test_denying_one_symptom_does_not_hide_another():
    assert detect_risk("no chest pain but I cannot breathe") == "emergency"


def test_audit_log_has_no_patient_data(caplog):
    """Log me sirf tool ka naam, nateeja aur request id. Naam ya phone nahin."""
    args = {"patient_name": "Asha Verma", "phone": "9876543210"}
    with caplog.at_level(logging.INFO, logger="hospital_agent.audit"):
        audit_tool_result(SimpleNamespace(name="request_booking"), args,
                          SimpleNamespace(invocation_id="e-123"), {"status": "needs_confirmation"})
    line = caplog.text
    assert "tool=request_booking outcome=needs_confirmation request_id=e-123" in line
    assert "Asha" not in line and "9876543210" not in line and "98XX" not in line


def test_guardrail_answers_without_calling_model():
    response = emergency_guardrail(None, _request("my father is unconscious"))
    assert "112" in response.content.parts[0].text
    assert emergency_guardrail(None, _request("OPD timing?")) is None


def test_mask_phone():
    assert mask_phone("9876543210") == "98XXXXXX10"


def test_features_switch_specialists_on_and_off():
    all_on = build_root_agent({"department_guide": True, "appointments": True, "hospital_faq": True})
    assert [a.name for a in all_on.sub_agents] == ["department_guide", "appointment_desk", "info_desk"]
    faq_off = build_root_agent({"department_guide": True, "appointments": True, "hospital_faq": False})
    assert "info_desk" not in [a.name for a in faq_off.sub_agents]


def test_every_tool_has_a_docstring_with_args():
    for tools in FEATURE_TOOLS.values():
        for tool in tools:
            doc = inspect.getdoc(tool) or ""
            assert len(doc) > 30, f"{tool.__name__} ka docstring bahut chhota hai"
            params = [p for p in inspect.signature(tool).parameters if p != "tool_context"]
            if params:
                assert "Args:" in doc, f"{tool.__name__} me Args: section nahin hai"
