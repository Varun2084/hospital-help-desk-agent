"""Browser app ki jaanch: page, bhasha ke saath session, emergency, aur scripted model se booking."""

from fastapi.testclient import TestClient
from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from hospital_agent.safety import EMERGENCY_MESSAGE_HI
from web_app import create_app

USER = "web_test_user_1"


class EchoModel(BaseLlm):
    """Nakli model: system instruction me jo bhasha likhi hai, wahi lautata hai."""
    model: str = "echo"

    async def generate_content_async(self, llm_request, stream=False):
        hindi = "chosen language is 'Hindi'" in llm_request.config.system_instruction
        text = "नमस्ते" if hindi else "Hello"
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=text)]))


def _client():
    service = InMemorySessionService()
    from hospital_agent.agent import COMMON_RULES
    agent = Agent(name="reception", model=EchoModel(), instruction="Desk. " + COMMON_RULES)
    runner = Runner(agent=agent, app_name="hospital_agent", session_service=service)
    return TestClient(create_app(runner=runner, session_service=service))


def _start(client, language):
    r = client.post("/api/start", json={"language": language, "user_id": USER})
    assert r.status_code == 200
    return r.json()["session_id"]


def test_page_and_logo_are_served():
    client = _client()
    assert "OPD Sahayak" in client.get("/").text
    assert client.get("/static/logo.svg").status_code == 200


def test_chosen_language_reaches_the_model():
    client = _client()
    for language, expected in [("Hindi", "नमस्ते"), ("English", "Hello")]:
        sid = _start(client, language)
        r = client.post("/api/chat", json={"user_id": USER, "session_id": sid, "message": "hi"})
        assert r.json()["replies"][0]["text"] == expected
        assert r.json()["replies"][0]["desk"] in ("रिसेप्शन", "Reception")


def test_emergency_is_answered_without_the_model():
    client = _client()
    sid = _start(client, "Hindi")
    r = client.post("/api/chat", json={"user_id": USER, "session_id": sid, "message": "papa ko seene me dard hai"})
    reply = r.json()["replies"][0]
    assert reply["kind"] == "emergency" and reply["text"] == EMERGENCY_MESSAGE_HI


def test_bad_input_is_rejected():
    client = _client()
    assert client.post("/api/start", json={"language": "French", "user_id": USER}).status_code == 422
    sid = _start(client, "English")
    assert client.post("/api/chat", json={"user_id": "web_other_user", "session_id": sid,
                                          "message": "hi"}).status_code == 404   # kisi aur ka session
    assert client.post("/api/chat", json={"user_id": USER, "session_id": sid,
                                          "message": "x" * 1001}).status_code == 422


def test_info_comes_from_config():
    info = _client().get("/api/info").json()
    assert info["hospital_name"].startswith("Demo Public Hospital") and info["disclaimer"]


class ScriptedBooking(BaseLlm):
    """Nakli model: pehle request_booking bulata hai, phir ek line bolta hai."""
    model: str = "scripted-booking"
    calls: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        if self.calls == 1:
            args = {"patient_name": "Asha Verma", "phone": "9876543210", "department_id": "cardiology",
                    "date": "2026-11-16", "time": "09:00"}
            part = types.Part(function_call=types.FunctionCall(name="request_booking", args=args))
        else:
            part = types.Part(text="Card dekh kar Confirm dabayein.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


def _booking_client():
    from conftest import register_patient

    from hospital_agent.tools import FEATURE_TOOLS
    register_patient("Asha Verma", "9876543210")
    service = InMemorySessionService()
    agent = Agent(name="appointment_desk", model=ScriptedBooking(), instruction="x",
                  tools=FEATURE_TOOLS["appointments"])
    runner = Runner(agent=agent, app_name="hospital_agent", session_service=service)
    return TestClient(create_app(runner=runner, session_service=service))


def test_chat_returns_a_confirm_card_and_the_button_books():
    client = _booking_client()
    sid = _start(client, "English")
    data = client.post("/api/chat", json={"user_id": USER, "session_id": sid, "message": "book 9 am"}).json()
    card = data["cards"][0]
    assert card["kind"] == "book" and card["summary"]["time"] == "09:00" and card["fingerprint"]
    body = {"user_id": USER, "session_id": sid, "action_id": card["action_id"], "fingerprint": card["fingerprint"]}
    assert client.post("/api/actions/confirm", json=body | {"user_id": "web_someone_else"}).status_code == 404
    wrong = client.post("/api/actions/confirm", json=body | {"fingerprint": "0" * 16}).json()
    assert wrong["result"]["status"] == "error"
    result = client.post("/api/actions/confirm", json=body).json()["result"]
    assert result["status"] == "booked"
    assert client.post("/api/actions/discard", json=body).json()["result"]["status"] == "booked"   # pakki: draft nahin


def test_discard_button_drops_the_draft():
    client = _booking_client()
    sid = _start(client, "Hindi")
    card = client.post("/api/chat", json={"user_id": USER, "session_id": sid, "message": "book"}).json()["cards"][0]
    body = {"user_id": USER, "session_id": sid, "action_id": card["action_id"], "fingerprint": card["fingerprint"]}
    assert client.post("/api/actions/discard", json=body).json()["result"]["status"] == "discarded"
    assert client.post("/api/actions/confirm", json=body).json()["result"]["status"] == "discarded"
