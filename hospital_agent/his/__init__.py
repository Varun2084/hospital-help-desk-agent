"""Kaun sa HIS chalega, .env tay karta hai:

    HIS_MODE=local      (default) isi project ka SQLite
    HIS_MODE=sandbox    HTTP sandbox (python -m his_sandbox), HIS_URL aur HIS_TIMEOUT ke saath
"""

import os
from functools import lru_cache

from hospital_agent.his.base import (  # noqa: F401
    HIS,
    Booking,
    BookingNotFound,
    HISError,
    HISTimeout,
    HISUnavailable,
    Slot,
    SlotTaken,
)
from hospital_agent.his.http import HttpHIS
from hospital_agent.his.local import LocalHIS


@lru_cache
def _http_his(url: str, timeout: float) -> HttpHIS:
    return HttpHIS(url, timeout=timeout)


def get_his() -> HIS:
    if os.environ.get("HIS_MODE", "local") == "sandbox":
        return _http_his(os.environ.get("HIS_URL", "http://127.0.0.1:8900"),
                         float(os.environ.get("HIS_TIMEOUT", "3")))
    return LocalHIS()
