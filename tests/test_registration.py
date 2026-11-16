"""Naye patient ka registration: arzi + Confirm button, umar/guardian ke niyam, dobara registration nahin."""

import pytest
from conftest import make_ctx

from hospital_agent import config, db
from hospital_agent.tools.actions import confirm_pending
from hospital_agent.tools.registration import request_registration

ARGS = {"full_name": "Asha  Verma", "age": 34, "gender": "female", "phone": "9876543210", "city": "Rewa"}


def _request(turn="turn-1", **changes):
    return request_registration(**(ARGS | changes), tool_context=make_ctx("register karna hai", turn=turn))


def _confirm(pending) -> dict:
    return confirm_pending(pending["action_id"], "patient_001", "s1", pending["fingerprint"])


def _patients() -> int:
    with db.connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


def test_request_alone_saves_nothing():
    pending = _request()
    assert pending["status"] == "needs_confirmation" and pending["summary"]["phone"] == "98XXXXXX10"
    assert pending["summary"]["full_name"] == "Asha Verma"          # faltu space hata
    assert "sahmat" in pending["consent_note"] and _patients() == 0


def test_confirm_button_creates_demo_id():
    pending = _request()
    assert _patients() == 0
    done = _confirm(pending)
    assert done["status"] == "registered" and done["patient_id"].startswith("DEMO-") and _patients() == 1
    assert done["phone"] == "98XXXXXX10"


def test_second_registration_returns_same_id():
    first = _confirm(_request())
    again = _request(turn="turn-3")
    assert again["status"] == "already_registered" and again["patient_id"] == first["patient_id"]
    assert _patients() == 1


@pytest.mark.parametrize("changes, word", [
    ({"age": 130}, "Umar"), ({"age": -1}, "Umar"), ({"gender": "x"}, "Gender"),
    ({"phone": "12345"}, "10 ankon"), ({"full_name": "A1"}, "naam"), ({"city": ""}, "gaon"),
])
def test_bad_details_are_rejected(changes, word):
    result = _request(**changes)
    assert result["status"] == "error" and word in result["message"]


def test_minor_needs_guardian():
    assert "guardian" in _request(age=9)["message"]
    pending = _request(age=9, guardian_name="Ramesh Verma", full_name="Chhoti Verma")
    assert pending["summary"]["guardian_name"] == "Ramesh Verma"


def test_flag_off_blocks_request_and_confirm(monkeypatch):
    pending = _request()
    monkeypatch.setattr(config, "load_features", lambda: {"appointments": True})
    assert _request()["status"] == "error"
    assert "band" in _confirm(pending)["message"]
    assert _patients() == 0
