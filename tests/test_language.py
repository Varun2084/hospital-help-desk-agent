"""Bhasha ka chunav: state me jaana, instruction me bharna, aur tay sandesh sahi bhasha me."""

from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

import run_demo
from hospital_agent.agent import COMMON_RULES, app
from hospital_agent.safety import EMERGENCY_MESSAGE_HI, emergency_guardrail, risk_message


class RecordingModel(BaseLlm):
    """Nakli model: jo system instruction mila, use yaad rakhta hai."""
    model: str = "recording"
    seen: list = []

    async def generate_content_async(self, llm_request, stream=False):
        self.seen.append(llm_request.config.system_instruction)
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text="ok")]))


async def _run(language: str | None, text: str, guardrail=False):
    model = RecordingModel(seen=[])
    agent = Agent(name="desk", model=model, instruction="Desk. " + COMMON_RULES,
                  before_model_callback=emergency_guardrail if guardrail else None)
    service = InMemorySessionService()
    runner = Runner(agent=agent, app_name="t", session_service=service)
    session = await service.create_session(app_name="t", user_id="u")
    if language:
        await run_demo.save_language(service, session, language)
    replies = []
    message = types.Content(role="user", parts=[types.Part(text=text)])
    async for event in runner.run_async(user_id="u", session_id=session.id, new_message=message):
        if event.is_final_response() and event.content:
            replies.append(event.content.parts[0].text)
    return model.seen, replies


async def test_chosen_language_reaches_the_instruction():
    seen, _ = await _run("Hindi", "cardiology kahan hai")
    assert "chosen language is 'Hindi'" in seen[0]
    assert "Devanagari" in seen[0]


async def test_no_choice_leaves_placeholder_empty():
    seen, _ = await _run(None, "hello")
    assert "chosen language is ''" in seen[0]


async def test_emergency_reply_follows_chosen_language():
    seen, replies = await _run("Hindi", "papa ko seene me dard hai", guardrail=True)
    assert seen == [] and replies == [EMERGENCY_MESSAGE_HI]   # model bulaya hi nahin gaya
    assert "112" in replies[0]


def test_risk_message_languages():
    assert "112" in risk_message("emergency", "Hindi") and "अभी" in risk_message("emergency", "Hindi")
    assert risk_message("emergency", "English").startswith("This may be an emergency")
    assert "14416" in risk_message("self_harm", "Hindi")


def test_language_menu_accepts_only_1_or_2(monkeypatch):
    answers = iter(["3", "hindi", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert run_demo.choose_language() == "Hindi"


def test_app_is_exposed_for_adk_web():
    assert app.name == "hospital_agent" and app.root_agent.name == "reception"
