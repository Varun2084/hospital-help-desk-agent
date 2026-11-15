"""Tests ki saajhi taiyari: har test ko apna khaali database, tay 'abhi' aur nakli tool_context milta hai."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from google.genai import types

from hospital_agent import db
from hospital_agent.tools import appointments

IST = ZoneInfo("Asia/Kolkata")
FIXED_NOW = datetime(2026, 11, 16, 7, 0, tzinfo=IST)  # Monday, subah 7 baje (OPD se pehle)


@pytest.fixture(autouse=True)
def isolated_db_and_clock(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(appointments, "now", lambda: FIXED_NOW)


def make_ctx(text: str = "", turn: str = "turn-1", user: str = "patient_001", session: str = "s1"):
    """ADK ke ToolContext ka chhota nakli roop: kaun patient, kaun si baat-cheet, kaun sa turn, kya kaha."""
    return SimpleNamespace(
        user_id=user,
        session=SimpleNamespace(id=session),
        invocation_id=turn,
        user_content=types.Content(role="user", parts=[types.Part(text=text)]),
    )


@pytest.fixture
def ctx():
    return make_ctx
