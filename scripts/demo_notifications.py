"""Lesson 8 demo: reception ka faisla -> scheduler confirm -> outbox -> worker -> patient inbox. Fake HIS ke saath.

    python scripts/demo_notifications.py

Interview wala flow, bina model aur API key:
  1. Patient A reschedule maange; scheduler me reschedule API nahin, to kaam reception ko
  2. Staff claim kare: patient ko abhi koi notification nahin
  3. Staff 'apply' kare: scheduler confirm, outbox me event; worker inbox tak
  4. Notification ka link updated appointment khole; Patient B ke liye wahi link 404
  5. Wahi event dobara process: inbox me ek hi item
  6. Lab report release: ek notification; dobara release: koi nahin
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP = tempfile.mkdtemp(prefix="opd_notify_")
os.environ["HOSPITAL_DB_PATH"] = os.path.join(TMP, "hospital.db")
os.environ["HIS_MODE"] = "sandbox"

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from seed_demo_patients import DEMO_STAFF, seed  # noqa: E402

from his_sandbox.server import SandboxServer  # noqa: E402
from hospital_agent import his, notifications, records  # noqa: E402
from hospital_agent.records_pdf import make_pdf  # noqa: E402
from web_app import create_app  # noqa: E402

A, B = "DEMO-PATIENT-A", "DEMO-PATIENT-B"
PHONES = {A: "9000000011", B: "9000000012"}


def client():
    return TestClient(create_app(session_service=InMemorySessionService()))


def login(c, pid):
    code = c.post("/api/login/start", json={"patient_id": pid, "phone": PHONES[pid]}).json()["demo_code"]
    c.post("/api/login/verify", json={"patient_id": pid, "code": code})
    return c


def staff_login(c, staff_id, phone):
    code = c.post("/api/staff/login/start", json={"staff_id": staff_id, "phone": phone}).json()["demo_code"]
    c.post("/api/staff/login/verify", json={"staff_id": staff_id, "code": code})
    return c


def row(test, result, ok):
    print(f"  {'PASS' if ok else 'FAIL'}  {test:<50} {result}")
    return ok


def main() -> None:
    with SandboxServer(os.path.join(TMP, "his.db")) as sandbox:
        os.environ["HIS_URL"] = sandbox.url
        his._http_his.cache_clear()
        refs = seed()
        ref = refs[A]
        patient, staff = login(client(), A), staff_login(client(), DEMO_STAFF[0][0], DEMO_STAFF[0][2])
        results = []

        alt = patient.get(f"/api/me/appointments/{ref}/alternatives").json()["alternatives"][0]
        card = patient.post(f"/api/me/appointments/{ref}/reschedule-preview", json={"slot_id": alt["slot_id"]}).json()
        httpx.post(f"{sandbox.url}/_sandbox/faults", json={"reschedule_unsupported": True})
        sent = patient.post(f"/api/me/reschedule-actions/{card['action_id']}/confirm",
                            json={"fingerprint": card["fingerprint"]}).json()["result"]
        httpx.post(f"{sandbox.url}/_sandbox/faults", json={"reschedule_unsupported": False})
        item_id = sent["queue_id"]
        print(f"Fake HIS: {sandbox.url}   A ki appointment {ref}; request {item_id} reception ko\n")

        staff.post(f"/api/staff/queue/{item_id}/claim")
        notifications.run_once()
        box = patient.get("/api/me/notifications").json()
        results.append(row("1. Claim hua, nateeja baaki: koi notification", box["unread"], box["notifications"] == []))

        done = staff.post(f"/api/staff/queue/{item_id}/resolve", json={"decision": "apply"}).json()
        delivered = [r for r in notifications.run_once() if r["status"] == "delivered"]
        box = patient.get("/api/me/notifications").json()
        item = box["notifications"][0] if box["notifications"] else {}
        results.append(row("2. Scheduler ne confirm kiya: ek notification", (len(delivered), item.get("body", {})
                           .get("en")), done.get("resolution") == "changed" and len(box["notifications"]) == 1))

        opened = patient.get(f"/api/me/appointments/{item['destination']['id']}").json()
        results.append(row("3. Link updated appointment khole", (opened["date"], opened["time"]),
                           (opened["date"], opened["time"]) == (alt["date"], alt["time"])))

        other = login(client(), B).get(f"/api/me/appointments/{item['destination']['id']}")
        results.append(row("4. Patient B wahi link khole", other.status_code, other.status_code == 404))

        again = notifications.replay(delivered[0]["event_id"])
        count = len(patient.get("/api/me/notifications").json()["notifications"])
        results.append(row("5. Wahi event dobara process", (again["created"], f"inbox: {count}"),
                           again["created"] is False and count == 1))

        pdf = make_pdf("Laboratory report", ["Synthetic"])
        first, second = records.release_lab_report("LAB-A-002", pdf), records.release_lab_report("LAB-A-002", pdf)
        notifications.run_once()
        kinds = [n["event_type"] for n in patient.get("/api/me/notifications").json()["notifications"]]
        results.append(row("6. Lab report release (do baar)", kinds,
                           first and not second and kinds.count("lab.report_released") == 1))

        print(f"\n{sum(results)}/{len(results)} checks passed")
        if not all(results):
            sys.exit(1)


if __name__ == "__main__":
    main()
