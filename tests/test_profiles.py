"""Har hospital profile (config folder) apne aap me sahi ho, aur poora code use chala sake."""

from pathlib import Path

import pytest

from hospital_agent import config
from hospital_agent.agent import SPECIALISTS, build_root_agent
from hospital_agent.tools import FEATURE_TOOLS

ROOT = Path(__file__).parent.parent
PROFILES = ["config", "config_rewa"]


@pytest.fixture
def profile(monkeypatch):
    def use(name):
        monkeypatch.setattr(config, "CONFIG_DIR", ROOT / name)
        config.reload_config()
    yield use
    config.reload_config()


@pytest.mark.parametrize("name", PROFILES)
def test_profile_is_valid_and_fully_wired(profile, name):
    profile(name)
    assert config.load_departments().departments
    assert config.load_hospital_info().topics
    features = config.load_features()
    assert set(features) == set(FEATURE_TOOLS) == set(SPECIALISTS)
    build_root_agent(features)


def test_rewa_profile_is_marked_unofficial_and_routes(profile):
    profile("config_rewa")
    from hospital_agent.tools.departments import suggest_department
    from hospital_agent.tools.faq import get_hospital_info
    assert "unofficial" in config.load_hospital_info().hospital_name
    assert suggest_department("पथरी का दर्द")["suggestions"][0]["id"] == "urology"
    assert len(config.load_departments().departments) == 8
    assert suggest_department("dialysis karwana hai")["suggestions"][0]["id"] == "nephrology"
    assert suggest_department("नवजात को पीलिया")["suggestions"][0]["id"] == "neonatology"
    assert get_hospital_info("OPD kab khulti hai?")["topic"] == "opd_timing"
    assert get_hospital_info("bachche ko bukhar hai")["topic"] == "general_opd"


@pytest.mark.parametrize("name, words", [("config", "Demo Public Hospital"),
                                         ("config_rewa", "Super Speciality Hospital, Rewa")])
def test_every_agent_names_the_configured_hospital(profile, name, words):
    """Bug: header me Rewa tha par reception 'Demo Public Hospital' bol raha tha."""
    profile(name)
    root = build_root_agent(config.load_features())
    for agent in [root, *root.sub_agents]:
        assert words in agent.instruction, agent.name
    if name == "config_rewa":
        assert all("Demo Public" not in a.instruction for a in [root, *root.sub_agents])
