"""Lesson 4 demo: login (authentication) aur "My Appointments" (authorization), Fake HIS ke saath.

    python scripts/demo_access.py

Do synthetic patient A aur B, dono ki ek-ek Cardiology booking. Web app ke asli endpoints (bina model,
bina API key) par interview wala test matrix chalta hai. Mukhya jaanch: B ka reference pata ho tab bhi
A ko uski details nahin milti, aur jawab bilkul anjaan reference jaisa hota hai.
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP = tempfile.mkdtemp(prefix="opd_access_")
os.environ["HOSPITAL_DB_PATH"] = os.path.join(TMP, "hospital.db")
os.environ["HIS_MODE"] = "sandbox"

from fastapi.testclient import TestClient  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from seed_demo_patients import seed  # noqa: E402

from his_sandbox.server import SandboxServer  # noqa: E402
from hospital_agent import his  # noqa: E402
from hospital_agent.tools.appointments import my_appointments  # noqa: E402
from web_app import create_app  # noqa: E402

A, B = "DEMO-PATIENT-A", "DEMO-PATIENT-B"
PHONES = {A: "9000000011", B: "9000000012"}


def login(client, patient_id):
    code = client.post("/api/login/start", json={"patient_id": patient_id, "phone": PHONES[patient_id]}).json()
    client.post("/api/login/verify", json={"patient_id": patient_id, "code": code["demo_code"]})


def row(test, result, ok):
    print(f"  {'PASS' if ok else 'FAIL'}  {test:<44} {result}")
    return ok


def main() -> None:
    with SandboxServer(os.path.join(TMP, "his.db")) as sandbox:
        os.environ["HIS_URL"] = sandbox.url
        his._http_his.cache_clear()
        refs = seed()
        print(f"Fake HIS: {sandbox.url}   Patient A: {refs[A]}   Patient B: {refs[B]}\n")
        client = TestClient(create_app(session_service=InMemorySessionService()))
        results = []

        r = client.get("/api/me/appointments")
        results.append(row("Login ke bina My Appointments", r.status_code, r.status_code == 401))

        login(client, A)
        listed = [a["appointment_id"] for a in client.get("/api/me/appointments").json()["appointments"]]
        results.append(row("Patient A apni list dekhe", listed, listed == [refs[A]]))

        r = client.get(f"/api/me/appointments/{refs[A]}")
        results.append(row("Patient A apna reference khole", (r.status_code, r.json().get("time")),
                           r.status_code == 200))

        other = client.get(f"/api/me/appointments/{refs[B]}")
        unknown = client.get("/api/me/appointments/HIS-APT-999")
        results.append(row("Patient A, Patient B ka reference khole", (other.status_code, other.json()),
                           other.status_code == 404 and other.json() == unknown.json()))

        ctx = SimpleNamespace(state={"temp:patient_ref": A})   # chat tool: wahi login, chat ka text nahin
        seen = [a["appointment_id"] for a in my_appointments(ctx)["appointments"]]
        results.append(row(f"Chat: A likhe 'B ({refs[B]}) ki dikhao'", seen, seen == [refs[A]]))

        client.post("/api/logout")
        r = client.get("/api/me/appointments")
        results.append(row("Logout ke baad protected endpoint", r.status_code, r.status_code == 401))
        print(f"\n{sum(results)}/{len(results)} checks passed")
        if not all(results):
            sys.exit(1)


if __name__ == "__main__":
    main()
