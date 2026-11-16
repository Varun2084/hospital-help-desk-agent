"""Lesson 5: Patient Dashboard aur Health Records (lab tests, prescriptions).

Interview ke 4 case:
  1. A ka processing test: status dikhta hai, report ka action nahin
  2. A ka released report aur issued prescription: dono sahi document khulte hain
  3. B, A ke document ka link khole: mana, aur record ki koi detail nahin
  4. A logout karke saved link khole: login dobara maanga jaata hai
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from google.adk.sessions import InMemorySessionService

from hospital_agent import config
from hospital_agent.agent import SPECIALISTS, build_root_agent
from hospital_agent.config import load_features
from hospital_agent.tools import FEATURE_TOOLS
from hospital_agent.tools.records import open_my_records
from web_app import create_app

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from seed_demo_patients import seed  # noqa: E402

A, B = "DEMO-PATIENT-A", "DEMO-PATIENT-B"
PHONES = {A: "9000000011", B: "9000000012"}


@pytest.fixture
def client():
    seed()
    return TestClient(create_app(session_service=InMemorySessionService()))


def login(client, patient_id):
    code = client.post("/api/login/start", json={"patient_id": patient_id, "phone": PHONES[patient_id]}).json()
    verified = client.post("/api/login/verify", json={"patient_id": patient_id, "code": code["demo_code"]})
    assert verified.status_code == 200


def test_case1_processing_test_shows_status_but_no_report(client):
    login(client, A)
    tests = {t["test_id"]: t for t in client.get("/api/me/lab-tests").json()["lab_tests"]}
    assert set(tests) == {"LAB-A-001", "LAB-A-002"}                       # sirf A ke
    lipid = tests["LAB-A-002"]
    assert (lipid["status"], lipid["step"], lipid["steps"], lipid["report_available"]) == ("processing", 3, 4, False)
    assert client.get("/api/me/lab-tests/LAB-A-002/report").status_code == 404   # release nahin: report nahin


def test_case2_released_report_and_prescription_open(client):
    login(client, A)
    report = client.get("/api/me/lab-tests/LAB-A-001/report")
    assert report.status_code == 200 and report.headers["content-type"] == "application/pdf"
    assert report.content.startswith(b"%PDF") and b"Complete Blood Count" in report.content
    assert "no-store" in report.headers["cache-control"]                  # browser cache me na rahe
    listed = client.get("/api/me/prescriptions").json()["prescriptions"]
    assert [p["prescription_id"] for p in listed] == ["RX-A-001"] and listed[0]["doctor"] == "Dr. Demo Cardiologist"
    doc = client.get("/api/me/prescriptions/RX-A-001/document")
    assert doc.status_code == 200 and b"Demo Patient A" in doc.content and b"SYNTHETIC" in doc.content


def test_case3_patient_b_cannot_open_patient_a_documents(client):
    login(client, B)
    for url in ("/api/me/lab-tests/LAB-A-001/report", "/api/me/prescriptions/RX-A-001/document"):
        r = client.get(url)
        assert r.status_code == 404 and r.json() == {"detail": "Document not found"}
        assert b"Demo Patient A" not in r.content and b"CBC" not in r.content
    unknown = client.get("/api/me/lab-tests/LAB-X-999/report")
    assert unknown.json() == {"detail": "Document not found"}             # anjaan aur doosre ka: ek jaisa
    assert [t["test_id"] for t in client.get("/api/me/lab-tests").json()["lab_tests"]] == ["LAB-B-001"]
    assert client.get("/api/me/lab-tests/LAB-B-001/report").status_code == 200


def test_case4_after_logout_a_saved_link_asks_for_login(client):
    login(client, A)
    url = "/api/me/prescriptions/RX-A-001/document"
    assert client.get(url).status_code == 200
    client.post("/api/logout")
    api = client.get(url)                                                  # app/fetch: 401
    page = client.get(url, headers={"accept": "text/html"}, follow_redirects=False)   # browser me khola link
    assert api.status_code == 401 and b"%PDF" not in api.content
    assert page.status_code == 303 and page.headers["location"] == "/?login=1"
    assert client.get("/api/me/lab-tests").status_code == 401


def test_chat_only_points_to_the_dashboard(monkeypatch):
    """Chat records nahin padhta: sirf dashboard ka tab kholne ka button."""
    monkeypatch.setattr(config, "load_features", lambda: {"health_records": True})
    result = open_my_records("lab_tests")
    assert result["status"] == "open_dashboard" and result["section"] == "lab_tests"
    assert "LAB-" not in str(result) and open_my_records("x-ray")["status"] == "error"


def test_flag_off_blocks_the_tool_itself(monkeypatch):
    monkeypatch.setattr(config, "load_features", lambda: {"health_records": False})
    result = open_my_records("lab_tests")
    assert result["status"] == "error" and "band" in result["message"]


def test_records_desk_is_wired():
    agent = build_root_agent({"health_records": True})
    assert [a.name for a in agent.sub_agents] == ["records_desk"]


def test_every_feature_is_wired_everywhere():
    """Har feature ke teeno hisse mojood hon: config flag, tools aur specialist agent."""
    assert set(load_features()) == set(FEATURE_TOOLS) == set(SPECIALISTS)
