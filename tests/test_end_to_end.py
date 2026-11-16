"""Asli ADK Runner ke saath poori booking, par Gemini ki jagah ek nakli (scripted) model.

Isse bina API key ke yeh jaancha jaata hai ki ADK hamare tools ko sahi tool_context deta hai,
audit log chalta hai, card asli events se banta hai, chat me 'ok' likhne se kuch book nahin hota,
aur Confirm button ka nateeja agle turn me model tak pahunchta hai.
"""

import logging

import pytest
from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from hospital_agent import db
from hospital_agent.cards import cards_from_event, record_outcome
from hospital_agent.safety import audit_tool_result
from hospital_agent.tools import FEATURE_TOOLS
from hospital_agent.tools.actions import confirm_pending

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


def _reply_after_seeing(seen: list):
    """Model ka agla kadam: jo baat-cheet use mili, use yaad rakho, aur ek line bolo."""
    def step(llm_request):
        seen.extend(p.text for c in llm_request.contents for p in (c.parts or []) if p.text)
        return types.Part(text="Theek hai.")
    return step


async def _say(runner, session, text) -> tuple[list[dict], list[dict]]:
    """Ek sandesh bhejta hai; us turn ke tool results aur Confirm cards lautata hai."""
    message = types.Content(role="user", parts=[types.Part(text=text)])
    results, cards = [], []
    async for event in runner.run_async(user_id="patient_001", session_id=session.id, new_message=message):
        cards.extend(cards_from_event(event))
        for part in (event.content.parts if event.content else []) or []:
            if part.function_response:
                results.append(part.function_response.response)
    return results, cards


async def _press_confirm(runner, session, card) -> dict:
    """Patient ne card par Confirm dabaya: backend, phir nateeja baat-cheet me."""
    result = confirm_pending(card["action_id"], "patient_001", session.id, card["fingerprint"])
    fresh = await runner.session_service.get_session(app_name="e2e", user_id="patient_001", session_id=session.id)
    await record_outcome(runner.session_service, fresh, card["kind"], "Confirm", result)
    return result


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
    seen = []
    runner, session = await _runner([
        _call("request_booking", **BOOK_ARGS),
        types.Part(text="Card par details dekh kar Confirm dabayein."),
        _reply_after_seeing(seen),
    ])
    with caplog.at_level(logging.INFO, logger="hospital_agent.audit"):
        results, cards = await _say(runner, session, "Cardiology me 16 Nov 09:00 book kar do")
    assert results[0]["status"] == "needs_confirmation" and _booked() == 0
    assert len(cards) == 1 and cards[0]["summary"]["weekday"] == "Monday"
    result = await _press_confirm(runner, session, cards[0])
    assert result["status"] == "booked" and _booked() == 1
    await _say(runner, session, "dhanyavaad")
    assert any("Patient pressed Confirm" in t and "booked" in t for t in seen)   # model ko pata chala
    assert "tool=request_booking outcome=needs_confirmation" in caplog.text
    assert "Asha" not in caplog.text and "9876543210" not in caplog.text


@pytest.mark.parametrize("typed", ["ok", "haan", "yes, confirm it"])
async def test_typing_yes_in_chat_books_nothing(typed):
    """Patient ka 'ok' summary padhne ka ishaara bhi ho sakta hai. Chat me kuch bhi likhne se booking nahin hoti."""
    runner, session = await _runner([
        _call("request_booking", **BOOK_ARGS),
        types.Part(text="Card dekhiye."),
        types.Part(text="Booking ho gayi!"),     # model jhooth bhi bole, database nahin badalta
    ])
    _, cards = await _say(runner, session, "Cardiology 16 Nov 09:00")
    await _say(runner, session, typed)
    assert _booked() == 0
    with db.connect() as conn:
        assert db.get_pending(conn, cards[0]["action_id"])["status"] == "pending"


async def test_registration_through_real_runner():
    """Registration bhi asli Runner me: model ki arzi, phir patient ka Confirm button."""
    agent = Agent(name="registration_desk", model=ScriptedModel(steps=[
        _call("request_registration", full_name="Asha Verma", age=34, gender="female",
              phone="9876543210", city="Rewa"),
        types.Part(text="Card dekh kar Confirm dabayein."),
    ]), tools=FEATURE_TOOLS["registration"])
    runner = InMemoryRunner(agent=agent, app_name="e2e")
    session = await runner.session_service.create_session(app_name="e2e", user_id="patient_001")
    _, cards = await _say(runner, session, "naya registration karna hai")
    assert cards[0]["kind"] == "register"
    result = await _press_confirm(runner, session, cards[0])
    assert result["status"] == "registered" and result["patient_id"].startswith("DEMO-")
