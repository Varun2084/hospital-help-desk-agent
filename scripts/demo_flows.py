"""Interview demo: HIS sandbox ke saath teen booking flow, bina model aur bina API key ke.

    python scripts/demo_flows.py

1. Normal booking
2. Ek hi slot par do patient ek saath (sirf ek jeetna chahiye)
3. HIS ka jawab timeout ho jaata hai; retry par wahi purani booking milti hai (doosri nahin banti)

Saara data synthetic hai. request_booking wahi tool hai jo agent bulata hai, aur confirm_pending wahi
function jo web app ka Confirm button bulata hai. Model ke bina, taaki demo har baar ek jaisa chale.
"""

import os
import sys
import tempfile
import threading
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP = tempfile.mkdtemp(prefix="opd_demo_")
os.environ["HOSPITAL_DB_PATH"] = os.path.join(TMP, "hospital.db")
os.environ["HIS_MODE"] = "sandbox"
os.environ["HIS_TIMEOUT"] = "1.5"

import httpx  # noqa: E402
from google.genai import types  # noqa: E402

from his_sandbox.server import SandboxServer  # noqa: E402
from hospital_agent.config import get_department  # noqa: E402
from hospital_agent.tools import common  # noqa: E402
from hospital_agent.tools.actions import confirm_pending  # noqa: E402
from hospital_agent.tools.appointments import check_available_slots, request_booking  # noqa: E402

DEPT = "cardiology"


def ctx(user: str, turn: str, text: str):
    """ADK ke ToolContext jaisa: kaun patient, kaun si baat-cheet, kaun sa turn, kya kaha."""
    return SimpleNamespace(user_id=user, session=SimpleNamespace(id="s-" + user), invocation_id=turn,
                           user_content=types.Content(role="user", parts=[types.Part(text=text)]))


def next_opd_day() -> str:
    dept = get_department(DEPT)
    day = common.today() + timedelta(days=1)
    while day.strftime("%a") not in dept.opd_days:
        day += timedelta(days=1)
    return day.isoformat()


def show(label: str, result: dict) -> None:
    keep = {k: result[k] for k in ("status", "appointment_id", "time", "message", "note") if k in result}
    print(f"  {label:<34} {keep}")


def book(user, name, phone, date, slot):
    """Model ki arzi (request_booking), aur ek function jo patient ka Confirm button dabata hai."""
    pending = request_booking(name, phone, DEPT, date, slot, ctx(user, "turn-1", f"{slot} book karo"))
    return pending, (lambda: confirm_pending(pending["action_id"], user, "s-" + user, pending["fingerprint"]))


def his_rows(sandbox, date, slot):
    r = httpx.get(f"{sandbox.url}/_sandbox/bookings", params={"department_id": DEPT, "date": date, "time": slot})
    return r.json()


def main() -> None:
    with SandboxServer(os.path.join(TMP, "his.db")) as sandbox:
        os.environ["HIS_URL"] = sandbox.url
        date = next_opd_day()
        slots = check_available_slots(DEPT, date)["free_slots"]
        print(f"HIS sandbox: {sandbox.url}   department: {DEPT}   date: {date}   free: {slots[:4]} ...\n")

        print("FLOW 1: normal booking")
        pending, confirm = book("patient_A", "Asha Verma", "9876543210", date, slots[0])
        show("request_booking (model ki arzi)", pending)
        show("Confirm button", confirm())
        print(f"  HIS me is slot ki bookings: {len(his_rows(sandbox, date, slots[0]))}\n")

        print("FLOW 2: ek hi slot par do patient ek saath")
        _, confirm_b = book("patient_B", "Ravi Kumar", "9123456780", date, slots[1])
        _, confirm_c = book("patient_C", "Meena Devi", "9988776655", date, slots[1])
        results = {}
        threads = [threading.Thread(target=lambda k, f: results.__setitem__(k, f()), args=(k, f))
                   for k, f in (("patient_B", confirm_b), ("patient_C", confirm_c))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for k in sorted(results):
            show(f"Confirm button: {k}", results[k])
        print(f"  HIS me is slot ki bookings: {len(his_rows(sandbox, date, slots[1]))}  (sirf ek)\n")

        print("FLOW 3: HIS ne booking kar di, par jawab timeout ho gaya")
        httpx.post(f"{sandbox.url}/_sandbox/faults", json={"lose_response_after_commit": 1, "delay_seconds": 4})
        pending, confirm = book("patient_D", "Sunita Patel", "9090909090", date, slots[2])
        show("request_booking (model ki arzi)", pending)
        started = time.time()
        show("Confirm button", confirm())
        print(f"  ...client ne {time.time() - started:.1f}s baad intezaar chhoda (HIS_TIMEOUT=1.5s)")
        rows = his_rows(sandbox, date, slots[2])
        print(f"  HIS me asal me: {[(r['reference'], r['idempotency_key']) for r in rows]}")
        show("Confirm button dobara (retry)", confirm())
        print(f"  HIS me is slot ki bookings: {len(his_rows(sandbox, date, slots[2]))}  (doosri nahin bani)")


if __name__ == "__main__":
    main()
