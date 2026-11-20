"""Lesson 6: appointment reschedule. Chat aur dashboard ek hi workflow; scheduler me ek transaction.

Sprint ke acceptance tests:
  1. Khaali slot chun kar confirm: naya date/time, purana slot khaali
  2. Preview ke baad naya slot kisi aur ne liya: purani appointment chalu, naye vikalp
  3. Confirm do baar: scheduler me ek hi badlaav
  4. Preview ke baad staff ne appointment badli: purana preview radd, abhi ki booking dikhe
  5. Scheduler ne badlaav kiya par jawab timeout: request_id se wahi nateeja
  6. Patient sirf chat me pasand bataye: preview bane, appointment button tak wahi rahe
"""

import httpx
import pytest
from conftest import make_ctx, register_patient
from fastapi.testclient import TestClient
from google.adk.agents import Agent
from google.adk.models import BaseLlm, LlmResponse
from google.adk.runners import InMemoryRunner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from his_sandbox.server import SandboxServer
from hospital_agent import db, his
from hospital_agent.cards import cards_from_event
from hospital_agent.his import slots
from hospital_agent.tools import FEATURE_TOOLS
from hospital_agent.tools.actions import confirm_pending
from web_app import create_app

A, B = "DEMO-PATIENT-A", "DEMO-PATIENT-B"
PHONES = {A: "9000000011", B: "9000000012"}
MONDAY, FRIDAY = "2026-11-16", "2026-11-20"


def slot(date, time):
    return slots.make_slot_id("cardiology", date, time)


@pytest.fixture
def ref():
    """A aur B registered; A ki Monday 09:00 Cardiology booking. A ka reference lautata hai."""
    register_patient("Demo Patient A", PHONES[A], patient_id=A)
    register_patient("Demo Patient B", PHONES[B], patient_id=B)
    return his.get_his().book("SEED-A", slot(MONDAY, "09:00"), A).reference


@pytest.fixture
def client():
    return TestClient(create_app(session_service=InMemorySessionService()))


def login(client, pid):
    code = client.post("/api/login/start", json={"patient_id": pid, "phone": PHONES[pid]}).json()["demo_code"]
    assert client.post("/api/login/verify", json={"patient_id": pid, "code": code}).status_code == 200


def preview(client, ref, date=FRIDAY, time="10:00"):
    r = client.post(f"/api/me/appointments/{ref}/reschedule-preview", json={"slot_id": slot(date, time)})
    assert r.status_code == 200, r.text
    return r.json()


def confirm(client, card):
    return client.post(f"/api/me/reschedule-actions/{card['action_id']}/confirm",
                       json={"fingerprint": card["fingerprint"]}).json()["result"]


def booking(ref):
    return his.get_his().find_for_patient(A, ref)


def test_1_available_slot_moves_and_old_slot_is_released(client, ref):
    login(client, A)
    alt = client.get(f"/api/me/appointments/{ref}/alternatives", params={"date": FRIDAY}).json()
    assert alt["current"]["time"] == "09:00" and alt["alternatives"][0]["location"]
    card = preview(client, ref)
    assert card["summary"]["current_date"] == MONDAY and card["summary"]["new_date"] == FRIDAY
    assert booking(ref).date == MONDAY                                    # preview se kuch nahin badla
    done = confirm(client, card)
    assert done["status"] == "rescheduled" and (done["date"], done["time"]) == (FRIDAY, "10:00")
    assert done["appointment_id"] == ref                                  # reference wahi (sandbox jaisa)
    listed = client.get("/api/me/appointments").json()["appointments"]
    assert [(a["date"], a["time"]) for a in listed] == [(FRIDAY, "10:00")]
    assert "09:00" in [s.time for s in his.get_his().open_slots("cardiology", MONDAY)]   # purana slot khaali


def test_2_target_taken_after_preview_keeps_original(client, ref):
    login(client, A)
    card = preview(client, ref)
    his.get_his().book("OTHER", slot(FRIDAY, "10:00"), B)                # B ne beech me le liya
    result = confirm(client, card)
    assert result["status"] == "error" and result["original_kept"]
    assert (booking(ref).date, booking(ref).time) == (MONDAY, "09:00")   # purani chalu
    fresh = [o["time"] for o in result["alternatives"]]
    assert fresh and "10:00" not in fresh


def test_3_double_click_makes_one_change(client, ref):
    login(client, A)
    card = preview(client, ref)
    first, second = confirm(client, card), confirm(client, card)
    assert first == second and first["status"] == "rescheduled"
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM reschedule_requests").fetchone()[0] == 1
    assert booking(ref).version == 2


def test_4_staff_move_after_preview_rejects_the_stale_preview(client, ref):
    login(client, A)
    card = preview(client, ref)
    with db.connect() as conn:                                            # staff ne Wednesday 11:00 kar di
        db.staff_move(conn, ref, slot("2026-11-18", "11:00"), "2026-11-18", "11:00")
    result = confirm(client, card)
    assert result["status"] == "error" and result["stale"]
    assert (result["current"]["date"], result["current"]["time"]) == ("2026-11-18", "11:00")
    assert (booking(ref).date, booking(ref).time) == ("2026-11-18", "11:00")   # staff wala hi rahe


def test_4b_keep_current_appointment_only_drops_the_preview(client, ref):
    login(client, A)
    card = preview(client, ref)
    kept = client.post(f"/api/me/reschedule-actions/{card['action_id']}/discard").json()["result"]
    assert kept["status"] == "discarded" and confirm(client, card)["status"] == "discarded"
    assert booking(ref).date == MONDAY


def test_only_own_upcoming_appointment_can_be_rescheduled(client, ref):
    login(client, B)
    assert client.get(f"/api/me/appointments/{ref}/alternatives").status_code == 404
    assert client.post(f"/api/me/appointments/{ref}/reschedule-preview",
                       json={"slot_id": slot(FRIDAY, "10:00")}).status_code == 404
    client.post("/api/logout")
    assert client.get(f"/api/me/appointments/{ref}/alternatives").status_code == 401


# ---------- Fake HIS ke saath (asli HTTP): timeout aur reception handover ----------

@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    with SandboxServer(str(tmp_path / "his.db")) as server:
        monkeypatch.setenv("HIS_MODE", "sandbox")
        monkeypatch.setenv("HIS_URL", server.url)
        monkeypatch.setenv("HIS_TIMEOUT", "0.5")
        his._http_his.cache_clear()
        yield server
    his._http_his.cache_clear()


def test_5_timeout_after_commit_recovers_the_same_change(client, ref_sandbox):
    sandbox, ref = ref_sandbox
    login(client, A)
    card = preview(client, ref)
    httpx.post(f"{sandbox.url}/_sandbox/faults", json={"lose_response_after_commit": 1, "delay_seconds": 2})
    first = confirm(client, card)
    assert first["status"] == "in_progress"                               # card: "Change verify ho raha hai"
    assert booking(ref).date == FRIDAY                                    # scheduler me asal me ho chuka
    again = confirm(client, card)                                         # "Status jaanchein"
    assert again["status"] == "rescheduled" and "doosra nahin hua" in again["note"]
    assert booking(ref).version == 2                                      # ek hi badlaav


def test_unsupported_reschedule_goes_to_reception(client, ref_sandbox):
    sandbox, ref = ref_sandbox
    login(client, A)
    card = preview(client, ref)
    httpx.post(f"{sandbox.url}/_sandbox/faults", json={"reschedule_unsupported": True})
    result = confirm(client, card)
    assert result["status"] == "reception_review" and booking(ref).date == MONDAY
    with db.connect() as conn:
        item = db.reception_queue(conn)[0]
    assert (item["kind"], item["patient_ref"], item["booking_ref"], item["status"]) == ("reschedule", A, ref, "pending")
    assert slot(FRIDAY, "10:00") in item["details"]


def test_staff_move_in_fake_his_rejects_stale_preview(client, ref_sandbox):
    sandbox, ref = ref_sandbox
    login(client, A)
    card = preview(client, ref)
    httpx.post(f"{sandbox.url}/_sandbox/staff-move", json={"booking_ref": ref, "new_slot_id": slot(MONDAY, "11:00")})
    result = confirm(client, card)
    assert result["stale"] and result["current"]["time"] == "11:00"


@pytest.fixture
def ref_sandbox(sandbox):
    register_patient("Demo Patient A", PHONES[A], patient_id=A)
    register_patient("Demo Patient B", PHONES[B], patient_id=B)
    return sandbox, his.get_his().book("SEED-A", slot(MONDAY, "09:00"), A).reference


# ---------- 6. Chat: pasand se preview, badlaav sirf button par ----------

class ChatModel(BaseLlm):
    """Nakli model: 'Friday ko shift karo' par my_appointments -> reschedule_options -> request_reschedule."""
    model: str = "scripted-reschedule"
    step: int = 0

    async def generate_content_async(self, llm_request, stream=False):
        last = llm_request.contents[-1].parts[0]
        self.step += 1
        response = last.function_response.response if last.function_response else None
        if self.step == 1:
            part = types.Part(function_call=types.FunctionCall(name="my_appointments", args={}))
        elif self.step == 2:
            ref = response["appointments"][0]["appointment_id"]
            part = types.Part(function_call=types.FunctionCall(name="reschedule_options", args={
                "appointment_id": ref, "date": FRIDAY, "part_of_day": "morning"}))
        elif self.step == 3:
            first = response["alternatives"][0]
            part = types.Part(function_call=types.FunctionCall(name="request_reschedule", args={
                "appointment_id": response["current"]["appointment_id"], "new_date": first["date"],
                "new_time": first["time"]}))
        else:
            part = types.Part(text="Card par naya aur purana samay dekh kar 'Confirm change' dabayein.")
        yield LlmResponse(content=types.Content(role="model", parts=[part]))


async def test_6_chat_preference_makes_a_preview_and_nothing_changes(ref):
    agent = Agent(name="appointment_desk", model=ChatModel(), tools=FEATURE_TOOLS["appointments"])
    runner = InMemoryRunner(agent=agent, app_name="e2e")
    session = await runner.session_service.create_session(app_name="e2e", user_id="browser_1")
    cards = []
    message = types.Content(role="user", parts=[types.Part(text="Meri Cardiology appointment Friday ko shift kar do")])
    async for event in runner.run_async(user_id="browser_1", session_id=session.id, new_message=message,
                                        state_delta={"temp:patient_ref": A}):
        cards.extend(cards_from_event(event))
    assert len(cards) == 1 and cards[0]["kind"] == "reschedule"
    s = cards[0]["summary"]
    assert (s["current_date"], s["current_time"], s["new_date"], s["new_time"]) == (MONDAY, "09:00", FRIDAY, "09:00")
    assert booking(ref).date == MONDAY                                    # button se pehle kuch nahin badla
    done = confirm_pending(cards[0]["action_id"], "browser_1", session.id, cards[0]["fingerprint"], A)
    assert done["status"] == "rescheduled" and booking(ref).date == FRIDAY


def test_chat_tools_need_a_login(ref):
    from hospital_agent.tools.reschedule import reschedule_options
    assert reschedule_options(ref, make_ctx("shift"))["status"] == "login_required"
    assert reschedule_options(ref, make_ctx("shift", patient=B))["status"] == "error"   # B ki nahin
