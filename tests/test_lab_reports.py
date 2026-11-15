import pytest

from hospital_agent import config
from hospital_agent.agent import SPECIALISTS, build_root_agent
from hospital_agent.config import load_features
from hospital_agent.tools import FEATURE_TOOLS
from hospital_agent.tools.lab_reports import get_lab_report_status


@pytest.fixture
def lab_on(monkeypatch):
    monkeypatch.setattr(config, "load_features", lambda: {"lab_reports": True})


def test_ready_report_shows_counter_and_nothing_else(lab_on):
    result = get_lab_report_status("lab-1001", "9876543210")
    assert result["report_status"] == "ready" and "collect_from" in result
    assert "test" not in result and "phone" not in result   # test ka naam aur phone jawab me nahin


def test_wrong_phone_reveals_nothing(lab_on):
    result = get_lab_report_status("LAB-1001", "9000000000")
    assert result == {"status": "error", "message": "Is report ID aur phone number se koi report nahin mili."}


def test_flag_off_blocks_the_tool_itself():
    """Flag band ho to tool seedha bulane par bhi kaam nahin karta (sirf agent se hatana kaafi nahin)."""
    result = get_lab_report_status("LAB-1001", "9876543210")
    assert result["status"] == "error" and "band" in result["message"]


def test_feature_flag_turns_lab_desk_on():
    agent = build_root_agent({"lab_reports": True})
    assert [a.name for a in agent.sub_agents] == ["lab_desk"]


def test_every_feature_is_wired_everywhere():
    """Har feature ke teeno hisse mojood hon: config flag, tools aur specialist agent."""
    assert set(load_features()) == set(FEATURE_TOOLS) == set(SPECIALISTS)
