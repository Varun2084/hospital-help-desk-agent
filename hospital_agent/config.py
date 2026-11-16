"""Config files (YAML) ko padhna aur unki jaanch (validation) karna."""

import functools
import os
import re
from datetime import date, time
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

PROJECT_DIR = Path(__file__).parent.parent
# Kaun sa hospital profile chalega: 'config' (demo) ya 'config_rewa'. .env me HOSPITAL_CONFIG_DIR se badlein.
CONFIG_DIR = PROJECT_DIR / os.environ.get("HOSPITAL_CONFIG_DIR", "config")
VALID_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class Department(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    name_hi: str
    building: str
    floor: str
    opd_days: list[str]
    opd_hours: str
    slot_minutes: int = Field(gt=0, le=120)
    keywords: list[str] = []
    active: bool = True

    @field_validator("opd_days")
    @classmethod
    def check_days(cls, days: list[str]) -> list[str]:
        wrong = [d for d in days if d not in VALID_DAYS]
        if wrong:
            raise ValueError(f"galat din {wrong}; sirf {VALID_DAYS} chalenge")
        return days

    @field_validator("opd_hours")
    @classmethod
    def check_hours(cls, hours: str) -> str:
        if not re.fullmatch(r"\d{2}:\d{2}-\d{2}:\d{2}", hours):
            raise ValueError("opd_hours 'HH:MM-HH:MM' format me hona chahiye, jaise '09:00-12:00'")
        start_s, end_s = hours.split("-")
        try:  # asli ghadi ka samay? '09:75' ya '26:99' yahin pakda jaata hai
            start, end = time.fromisoformat(start_s), time.fromisoformat(end_s)
        except ValueError as e:
            raise ValueError(f"opd_hours me galat samay: {hours}") from e
        if start >= end:
            raise ValueError("OPD ka shuru hone ka samay khatm hone se pehle hona chahiye")
        return hours

    @model_validator(mode="after")
    def check_usable_schedule(self) -> "Department":
        """Chalu department me kam se kam ek din aur ek poora slot hona chahiye."""
        if not self.active:
            return self
        if not self.opd_days:
            raise ValueError(f"{self.id}: active department ke opd_days khaali hain")
        start_s, end_s = self.opd_hours.split("-")
        start, end = time.fromisoformat(start_s), time.fromisoformat(end_s)
        minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
        if minutes < self.slot_minutes:
            raise ValueError(f"{self.id}: opd_hours me {self.slot_minutes} minute ka ek bhi slot nahin banta")
        return self


class DepartmentCatalog(BaseModel):
    departments: list[Department]

    @model_validator(mode="after")
    def check_unique_ids(self) -> "DepartmentCatalog":
        ids = [d.id for d in self.departments]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"department id dohrayi gayi hai: {duplicates}")
        return self


class InfoTopic(BaseModel):
    id: str
    keywords: list[str]
    answer: str
    source: str
    verified_on: date  # yeh jawab aakhri baar kab jaancha gaya


class HospitalInfo(BaseModel):
    hospital_name: str
    disclaimer: str
    helpdesk: str  # jab bot ke paas jawab na ho to patient ko kahan bhejein
    topics: list[InfoTopic]


def _read_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


@lru_cache
def load_departments() -> DepartmentCatalog:
    return DepartmentCatalog.model_validate(_read_yaml("departments.yaml"))


@lru_cache
def load_hospital_info() -> HospitalInfo:
    return HospitalInfo.model_validate(_read_yaml("hospital_info.yaml"))


@lru_cache
def load_features() -> dict[str, bool]:
    return _read_yaml("features.yaml")["features"]


def reload_config() -> None:
    """Config file badalne ke baad cache saaf karta hai, taaki naya data padha jaye."""
    load_departments.cache_clear()
    load_hospital_info.cache_clear()
    load_features.cache_clear()


def get_department(department_id: str) -> Department | None:
    for dept in load_departments().departments:
        if dept.id == department_id:
            return dept
    return None


def active_departments() -> list[Department]:
    return [d for d in load_departments().departments if d.active]


def feature_required(feature: str):
    """Decorator: feature ka flag band ho to tool chalne se mana kar deta hai.
    Is tarah flag sirf agent ki list par nahin, har tool ke andar bhi laagu hota hai."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not load_features().get(feature, False):
                return {"status": "error", "message": f"'{feature}' feature abhi band hai."}
            return func(*args, **kwargs)
        return wrapper
    return decorator
