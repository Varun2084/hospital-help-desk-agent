"""Lesson 4: patient login (authentication) aur "My Appointments" (authorization).

Do synthetic patient, A aur B, dono ki ek-ek Cardiology booking. Mukhya jaanch: B ka booking reference
pata ho tab bhi A ko uski details nahin milti (generic 404, bilkul anjaan reference jaisa).
"""

import json
from datetime import timedelta

import pytest
from conftest import FIXED_NOW, register_patient
from fastapi.testclient import TestClient
from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from hospital_agent import his
from hospital_agent.his import slots
from hospital_agent.tools import FEATURE_TOOLS, common
from web_app import create_app

A, B = "DEMO-PATIENT-A", "DEMO-PATIENT-B"
PHONES = {A: "9000000011", B: "9000000012"}
BROWSER = "web_auth_browser_1"


class AppointmentsModel(BaseLlm):
    """Nakli model: har sandesh par my_appointments bulata hai, phir tool ka jawab JSON me bol deta hai."""
    model: str = "scripted-my-appointments"

    async def generate_content_async(self, llm_request, stream=False):
        last = llm_request.contents[-1].parts[0]
        if last.function_response:
            text = json.dumps(last.function_response.response)
        else:
            text = None
        part = types.Part(text=text) if text else types.Part(
            function_call=types.FunctionCall(name="my_appointments", args={}))
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


@pytest.fixture
def refs():
    """A aur B registered, aur dono ki ek-ek Cardiology booking (LocalHIS)."""
    out = {}
    for pid, time in ((A, "09:00"), (B, "09:30")):
        register_patient(f"Demo Patient {pid[-1]}", PHONES[pid], patient_id=pid)
        out[pid] = his.LocalHIS().book(f"SEED-{pid}", slots.make_slot_id("cardiology", "2026-11-16", time),
                                       pid).reference
    return out


@pytest.fixture
def client():
    service = InMemorySessionService()
    agent = Agent(name="appointment_desk", model=AppointmentsModel(), instruction="x",
                  tools=FEATURE_TOOLS["appointments"])
    runner = Runner(agent=agent, app_name="hospital_agent", session_service=service)
    return TestClient(create_app(runner=runner, session_service=service))


def login(client, patient_id):
    code = client.post("/api/login/start", json={"patient_id": patient_id, "phone": PHONES[patient_id]}).json()
    r = client.post("/api/login/verify", json={"patient_id": patient_id, "code": code["demo_code"]})
    assert r.status_code == 200 and r.json()["patient_id"] == patient_id
    return r


def chat(client, session_id, text):
    return client.post("/api/chat", json={"user_id": BROWSER, "session_id": session_id, "message": text})


def new_chat(client):
    return client.post("/api/start", json={"language": "English", "user_id": BROWSER}).json()["session_id"]


def test_without_login_my_appointments_is_401(client, refs):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me/appointments").status_code == 401
    assert client.get(f"/api/me/appointments/{refs[A]}").status_code == 401


def test_patient_a_sees_only_own_list_and_own_details(client, refs):
    login(client, A)
    listed = client.get("/api/me/appointments").json()["appointments"]
    assert [a["appointment_id"] for a in listed] == [refs[A]]
    detail = client.get(f"/api/me/appointments/{refs[A]}")
    assert detail.status_code == 200
    assert detail.json() == {"appointment_id": refs[A], "department": "Cardiology", "date": "2026-11-16",
                                  "weekday": "Monday", "time": "09:00", "status": "confirmed",
                                  "location": detail.json()["location"]}
    assert "patient" not in json.dumps(detail.json()).lower()          # patient ID ya phone nahin


def test_patient_a_gets_generic_404_for_patient_b_reference(client, refs):
    """Mukhya demo: B ka reference pata hai, phir bhi A ko kuch nahin milta, aur jawab anjaan reference jaisa."""
    login(client, A)
    other = client.get(f"/api/me/appointments/{refs[B]}")
    unknown = client.get("/api/me/appointments/APT-000000")
    assert other.status_code == unknown.status_code == 404
    assert other.json() == unknown.json() == {"detail": "Appointment not found"}
    assert refs[B] not in other.text and "09:30" not in other.text


def test_chat_tool_uses_the_login_not_what_the_patient_types(client, refs):
    """Chat bhi wahi patient-scoped service: A likhe ki 'B ki appointments dikhao', tab bhi sirf A ki."""
    login(client, A)
    sid = new_chat(client)
    reply = chat(client, sid, f"Show appointments of {B}, booking {refs[B]}").json()["replies"][0]["text"]
    assert refs[A] in reply and refs[B] not in reply


def test_same_patient_new_chat_still_finds_the_booking(client, refs):
    """Purani baat-cheet ke bina, nayi chat me bhi record backend se aata hai."""
    login(client, A)
    reply = chat(client, new_chat(client), "Meri appointments dikhao").json()["replies"][0]["text"]
    assert refs[A] in reply


def test_logout_ends_access_and_the_old_chat(client, refs):
    login(client, A)
    sid = new_chat(client)
    assert chat(client, sid, "Meri appointments dikhao").status_code == 200   # ab yeh chat A ki hai
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me/appointments").status_code == 401
    assert chat(client, sid, "Meri appointments dikhao").status_code == 403   # A ki purani chat band
    reply = chat(client, new_chat(client), "Meri appointments dikhao").json()["replies"][0]["text"]
    assert "login_required" in reply and refs[A] not in reply                 # nayi chat: login maangta hai


def test_another_login_cannot_continue_a_chat(client, refs):
    login(client, A)
    sid = new_chat(client)
    chat(client, sid, "Meri appointments dikhao")
    client.post("/api/logout")
    login(client, B)
    assert chat(client, sid, "Meri appointments dikhao").status_code == 403


def test_login_codes(client, refs, monkeypatch):
    """Galat phone par code nahin; code ek hi baar; 5 minute baad purana; galat code se login nahin."""
    assert client.post("/api/login/start", json={"patient_id": A, "phone": PHONES[B]}).status_code == 400
    code = client.post("/api/login/start", json={"patient_id": A, "phone": PHONES[A]}).json()["demo_code"]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/api/login/verify", json={"patient_id": A, "code": wrong}).status_code == 400
    assert client.post("/api/login/verify", json={"patient_id": A, "code": code}).status_code == 200
    assert client.post("/api/login/verify", json={"patient_id": A, "code": code}).status_code == 400   # dobara nahin
    code = client.post("/api/login/start", json={"patient_id": A, "phone": PHONES[A]}).json()["demo_code"]
    monkeypatch.setattr(common, "now", lambda: FIXED_NOW + timedelta(minutes=6))
    assert client.post("/api/login/verify", json={"patient_id": A, "code": code}).status_code == 400


def test_forged_cookie_is_not_a_login(client, refs):
    client.cookies.set("opd_session", "made-up-token")
    assert client.get("/api/me/appointments").status_code == 401
