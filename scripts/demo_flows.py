"""Interview demo: Fake HIS (alag server) ke saath teen booking flow, bina model aur bina API key ke.

    python scripts/demo_flows.py

0. Synthetic patients ka registration (booking sirf registered patient ki hoti hai)
1. Normal booking: card par scheduler ka reference (HIS-APT-001)
2. Ek hi slot par do patient ek saath: sirf ek jeetta hai, doosre ko naye khaali samay milte hain
3. HIS ne booking save ki par jawab kho gaya (timeout); usi request_id se wahi reference wapas milta hai

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
from hospital_agent.tools.appointments import (  # noqa: E402
    check_available_slots,
    request_booking,
)
from hospital_agent.tools.registration import request_registration  # noqa: E402

PATIENTS = [  # synthetic: interview recording me asli naam ya number nahin
    ("patient_A", "Demo Patient A", "9000000001"),
    ("patient_B", "Demo Patient B", "9000000002"),
    ("patient_C", "Demo Patient C", "9000000003"),
    ("patient_D", "Demo Patient D", "9000000004"),
]

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
    keep = {k: result[k] for k in ("status", "patient_id", "appointment_id", "time", "message", "free_slots", "note")
            if k in result}
    print(f"  {label:<34} {keep}")


def register(user, name, phone) -> str:
    """Registration bhi wahi do kadam: arzi, phir Confirm button. DEMO patient ID lautata hai."""
    pending = request_registration(name, 35, "female", phone, "Rewa", ctx(user, "reg-1", "register"))
    return confirm_pending(pending["action_id"], user, "s-" + user, pending["fingerprint"])["patient_id"]


def book(user, name, phone, date, slot):
    """Model ki arzi (request_booking), aur ek function jo patient ka Confirm button dabata hai."""
    pending = request_booking(name, phone, DEPT, date, slot, ctx(user, "turn-1", f"{slot} book karo"))
    return pending, (lambda: confirm_pending(pending["action_id"], user, "s-" + user, pending["fingerprint"]))


def his_rows(sandbox, pending):
    """Fake HIS me is slot (slot_id) par kitni bookings hain."""
    slot_id = "SLOT-{}-{}-{}".format(DEPT, pending["summary"]["date"].replace("-", ""),
                                     pending["summary"]["time"].replace(":", ""))
    return httpx.get(f"{sandbox.url}/_sandbox/bookings", params={"slot_id": slot_id}).json()


def main() -> None:
    with SandboxServer(os.path.join(TMP, "his.db")) as sandbox:
        os.environ["HIS_URL"] = sandbox.url
        date = next_opd_day()
        slots = check_available_slots(DEPT, date)["free_slots"]
        print(f"Fake HIS: {sandbox.url}   department: {DEPT}   date: {date}   free: {slots[:4]} ...\n")

        print("FLOW 0: pehle registration (synthetic patients)")
        print("  " + "   ".join(f"{name} -> {register(user, name, phone)}" for user, name, phone in PATIENTS) + "\n")

        print("FLOW 1: normal booking")
        pending, confirm = book("patient_A", "Demo Patient A", "9000000001", date, slots[0])
        show("request_booking (model ki arzi)", pending)
        show("Confirm button", confirm())
        print(f"  Fake HIS me is slot ki bookings: {len(his_rows(sandbox, pending))}\n")

        print("FLOW 2: ek hi slot par do patient ek saath")
        pending_b, confirm_b = book("patient_B", "Demo Patient B", "9000000002", date, slots[1])
        _, confirm_c = book("patient_C", "Demo Patient C", "9000000003", date, slots[1])
        results = {}
        threads = [threading.Thread(target=lambda k, f: results.__setitem__(k, f()), args=(k, f))
                   for k, f in (("patient_B", confirm_b), ("patient_C", confirm_c))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for k in sorted(results):
            show(f"Confirm button: {k}", results[k])
        print(f"  Fake HIS me is slot ki bookings: {len(his_rows(sandbox, pending_b))}  (sirf ek)\n")

        print("FLOW 3: HIS ne booking kar di, par jawab timeout ho gaya")
        httpx.post(f"{sandbox.url}/_sandbox/faults", json={"lose_response_after_commit": 1, "delay_seconds": 4})
        pending, confirm = book("patient_D", "Demo Patient D", "9000000004", date, slots[2])
        show("request_booking (model ki arzi)", pending)
        started = time.time()
        show("Confirm button", confirm())
        print(f"  ...client ne {time.time() - started:.1f}s baad intezaar chhoda (HIS_TIMEOUT=1.5s)")
        rows = his_rows(sandbox, pending)
        print(f"  Fake HIS me asal me: {[(r['booking_ref'], r['request_id']) for r in rows]}")
        show("Status jaanchein (wahi request_id)", confirm())
        print(f"  Fake HIS me is slot ki bookings: {len(his_rows(sandbox, pending))}  (doosri nahin bani)")


if __name__ == "__main__":
    main()
