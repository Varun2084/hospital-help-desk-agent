import pytest
from pydantic import ValidationError

from hospital_agent.config import (
    DepartmentCatalog,
    active_departments,
    load_departments,
)


def test_config_loads_and_ids_are_unique():
    catalog = load_departments()
    ids = [d.id for d in catalog.departments]
    assert len(ids) == len(set(ids))


def test_every_active_department_has_keywords():
    for dept in active_departments():
        assert dept.keywords, f"{dept.id} ke keywords khaali hain; symptom routing kaam nahin karega"


def test_duplicate_id_is_rejected():
    dept = load_departments().departments[0].model_dump()
    with pytest.raises(ValidationError, match="dohrayi"):
        DepartmentCatalog.model_validate({"departments": [dept, dept]})


def test_bad_opd_hours_are_rejected():
    dept = load_departments().departments[0].model_dump()
    dept["opd_hours"] = "9 se 12"
    with pytest.raises(ValidationError, match="HH:MM"):
        DepartmentCatalog.model_validate({"departments": [dept]})


def test_bad_day_is_rejected():
    dept = load_departments().departments[0].model_dump()
    dept["opd_days"] = ["Monday"]
    with pytest.raises(ValidationError, match="galat din"):
        DepartmentCatalog.model_validate({"departments": [dept]})


@pytest.mark.parametrize("hours", ["09:75-26:99", "25:00-26:00", "12:00-09:00"])
def test_impossible_clock_times_are_rejected(hours):
    """Review me mila: '09:75-26:99' pehle paas ho jaata tha."""
    dept = load_departments().departments[0].model_dump()
    dept["opd_hours"] = hours
    with pytest.raises(ValidationError):
        DepartmentCatalog.model_validate({"departments": [dept]})


def test_active_department_needs_a_usable_schedule():
    dept = load_departments().departments[0].model_dump()
    with pytest.raises(ValidationError, match="opd_days khaali"):
        DepartmentCatalog.model_validate({"departments": [dept | {"opd_days": []}]})
    with pytest.raises(ValidationError, match="ek bhi slot nahin"):
        DepartmentCatalog.model_validate({"departments": [dept | {"opd_hours": "09:00-09:10", "slot_minutes": 30}]})
    DepartmentCatalog.model_validate({"departments": [dept | {"opd_days": [], "active": False}]})
