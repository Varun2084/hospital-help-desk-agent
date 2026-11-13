"""Asli ADK Runner ke saath poori booking, par Gemini ki jagah ek nakli (scripted) model.

Isse bina API key ke yeh jaancha jaata hai ki ADK hamare tools ko sahi tool_context deta hai,
audit log chalta hai, aur 'usi turn me confirm' asli runner me bhi ruk jaata hai.
"""

import logging

from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from hospital_agent import db
from hospital_agent.safety import audit_tool_result
from hospital_agent.tools import FEATURE_TOOLS

BOOK_ARGS = {"patient_name": "Asha Verma", "phone": "9876543210", "department_id": "cardiology",
             "date": "2026-11-16", "time": "09:00"}


class ScriptedModel(BaseLlm):
    """Nakli model: pehle se likhe hue kadam ek-ek karke lautata hai."""
    model: str = "scripted"
    steps: list = []

    async def generate_content_async(self, llm_request, stream=False):
        step = self.steps.pop(0)
        if callable(step):  # pichhle tool ke jawab se agla kadam banana
            step = step(llm_request)
        yield LlmResponse(content=types.Content(role="model", parts=[step]))


def _call(name, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def _last_tool_result(llm_request) -> dict:
    for content in reversed(llm_request.contents):
        for part in content.parts or []:
            if part.function_response:
                return part.function_response.response
    return {}


def _confirm_last_action(llm_request):
    return _call("confirm_action", action_id=_last_tool_result(llm_request)["action_id"])


async def _say(runner, session, text) -> list[dict]:
    """Ek sandesh bhejta hai aur us turn ke saare tool results lautata hai."""
    message = types.Content(role="user", parts=[types.Part(text=text)])
    results = []
    async for event in runner.run_async(user_id="patient_001", session_id=session.id, new_message=message):
        for part in (event.content.parts if event.content else []) or []:
            if part.function_response:
                results.append(part.function_response.response)
    return results


def _booked() -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM appointments WHERE status = 'booked'").fetchone()[0]


async def _runner(steps):
    agent = Agent(name="appointment_desk", model=ScriptedModel(steps=steps),
                  tools=FEATURE_TOOLS["appointments"], after_tool_callback=audit_tool_result)
    runner = InMemoryRunner(agent=agent, app_name="e2e")
    session = await runner.session_service.create_session(app_name="e2e", user_id="patient_001")
    return runner, session


async def test_full_booking_through_real_runner(caplog):
    runner, session = await _runner([
        _call("request_booking", **BOOK_ARGS),
        types.Part(text="Summary: ... Kya main ise pakka karun?"),
        _confirm_last_action,   # doosre turn me: pichhli arzi ka action_id
        types.Part(text="Booking ho gayi."),
    ])
    with caplog.at_level(logging.INFO, logger="hospital_agent.audit"):
        first = await _say(runner, session, "Cardiology me 16 Nov 09:00 book kar do")
        assert first[0]["status"] == "needs_confirmation" and _booked() == 0
        second = await _say(runner, session, "haan, pakka kar do")
    assert second[0]["status"] == "booked" and _booked() == 1
    assert "tool=confirm_action outcome=booked" in caplog.text
    assert "Asha" not in caplog.text and "9876543210" not in caplog.text


async def test_model_confirming_by_itself_is_stopped_by_code():
    """Model summary sunaye bina usi turn me confirm_action bula deta hai: code mana karta hai."""
    runner, session = await _runner([
        _call("request_booking", **BOOK_ARGS),
        _confirm_last_action,
        types.Part(text="..."),
    ])
    results = await _say(runner, session, "haan haan jaldi book kar do 09:00")
    assert [r["status"] for r in results] == ["needs_confirmation", "error"]
    assert _booked() == 0
