"""Lesson 8: patient ko apne aap update (in-app bell aur inbox).

Ek pakka badlaav = ek notification:

    hospital ka nateeja save  ──(usi DB transaction me)──>  notification_outbox me event
    worker (app ke andar, ya `python -m hospital_agent.notifications`)  ──>  patient_notifications (inbox)

  - Event tabhi banta hai jab nateeja PAKKA ho (scheduler ne confirm kiya, staff ne band kiya, lab ne release kiya).
    Timeout par pehle nateeja milaya jaata hai (Check status / reception verify); tab tak koi notification nahin.
  - event_id tay hota hai (jaise "appointment.rescheduled:ACT-1234"); inbox me event_id UNIQUE. Worker ek event
    do baar chalaye, ya beech me ruk kar dobara uthaye, to bhi inbox me ek hi item.
  - Restart: event database me hai, isliye agla worker use utha leta hai.
  - Message hospital ke approved Hindi/English template se (AI nahin likhta), aur sirf generic: "appointment update
    ho gayi". Date, report ya dawa ki details sirf login ke baad dashboard me (protected page).
  - Reminder bhejne se pehle worker scheduler se abhi ki haalat dekhta hai: appointment cancel ho gayi ya samay
    badal gaya to purana reminder chhod deta hai.

SMS / WhatsApp / email baad me isi pipeline ke CHANNELS me judenge (hospital ki channel preference aur
approved template ke saath); unme bhi yahi generic sandesh jaayega.
"""

import json
import time
import uuid
from datetime import date as Date
from datetime import datetime, timedelta

from hospital_agent import db, his
from hospital_agent.tools import common

# Hospital ke approved templates. Inme koi record detail nahin; wording badalni ho to yahi ek jagah.
TEMPLATES = {
    "appointment.rescheduled": {
        "hi": ("अपॉइंटमेंट अपडेट", "आपकी अपॉइंटमेंट अपडेट हो गई है।"),
        "en": ("Appointment updated", "Your appointment has been updated."),
    },
    "reception.request_resolved": {
        "hi": ("हेल्पडेस्क अपडेट", "आपकी हेल्पडेस्क रिक्वेस्ट पर अपडेट है।"),
        "en": ("Helpdesk update", "There is an update on your helpdesk request."),
    },
    "lab.report_released": {
        "hi": ("नई लैब रिपोर्ट", "आपके डैशबोर्ड में एक नई लैब रिपोर्ट उपलब्ध है।"),
        "en": ("New lab report", "A new lab report is available in your dashboard."),
    },
    "appointment.reminder": {
        "hi": ("अपॉइंटमेंट रिमाइंडर", "आपकी आने वाली अपॉइंटमेंट है। विवरण डैशबोर्ड में देखें।"),
        "en": ("Appointment reminder", "You have an upcoming appointment. See the details in your dashboard."),
    },
}
# Notification tap karne par dashboard ka kaunsa protected record khulega
VIEWS = {"appointment.rescheduled": "appointment", "reception.request_resolved": "request",
         "lab.report_released": "lab_test", "appointment.reminder": "appointment"}

REMINDER_BEFORE = timedelta(hours=24)
REMINDER_MIN_GAP = timedelta(hours=2)   # appointment isse kam door ho to reminder nahin (patient ne abhi dekha)
LEASE = timedelta(seconds=60)           # worker ne uthaya event itni der kisi aur ko nahin milta
MAX_ATTEMPTS = 5


def _ts(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def _event(event_type: str, key: str, patient_ref: str, record_ref: str, payload: dict | None = None,
           due_at: datetime | None = None) -> dict:
    return {"event_id": f"{event_type}:{key}", "event_type": event_type, "patient_ref": patient_ref,
            "record_ref": record_ref, "payload": payload or {}, "due_at": _ts(due_at or common.now())}


# ---------- events (pakka nateeja save karne wala code inhe usi transaction me deta hai) ----------

def rescheduled(request_id: str, booking) -> list[dict]:
    """Scheduler ne badlaav confirm kiya: 'appointment updated' + naye samay ka reminder."""
    events = [_event("appointment.rescheduled", request_id, booking.patient_ref, booking.reference,
                     {"date": booking.date, "time": booking.time})]
    return events + reminder(booking)


def booked(booking) -> list[dict]:
    """Nayi booking: patient ne card par khud dekha, isliye sirf reminder."""
    return reminder(booking)


def request_resolved(item_id: str, patient_ref: str, resolution: str) -> list[dict]:
    return [_event("reception.request_resolved", item_id, patient_ref, item_id, {"resolution": resolution})]


def lab_report_released(test_id: str, patient_ref: str) -> dict:
    return _event("lab.report_released", test_id, patient_ref, test_id)


def appointment_at(booking) -> datetime:
    return datetime.combine(Date.fromisoformat(booking.date),
                            datetime.strptime(booking.time, "%H:%M").time(), tzinfo=db.IST)


def reminder(booking) -> list[dict]:
    """Appointment se 24 ghante pehle (ya abhi, agar 24 ghante se kam bache ho). Har samay ka alag event:
    samay badla to naya reminder; purana worker khud chhod dega."""
    when, moment = appointment_at(booking), common.now()
    if when - moment < REMINDER_MIN_GAP:
        return []
    due = max(when - REMINDER_BEFORE, moment)
    return [_event("appointment.reminder", f"{booking.reference}:{booking.date}T{booking.time}", booking.patient_ref,
                   booking.reference, {"date": booking.date, "time": booking.time}, due)]


# ---------- worker ----------

def _render(event) -> dict:
    t = TEMPLATES[event["event_type"]]
    return {"id": "NTF-" + uuid.uuid4().hex[:8].upper(), "event_id": event["event_id"],
            "patient_ref": event["patient_ref"], "event_type": event["event_type"],
            "title_hi": t["hi"][0], "body_hi": t["hi"][1], "title_en": t["en"][0], "body_en": t["en"][1],
            "destination": json.dumps({"view": VIEWS[event["event_type"]], "id": event["record_ref"]}),
            "created_at": db.now_text()}


def deliver_in_app(event) -> tuple[str, bool]:
    """Inbox channel. (notification id, naya bana?) Dobara chale to wahi item lautata hai."""
    with db.connect() as conn:
        item, created = db.insert_notification(conn, _render(event))
    return item["id"], created


CHANNELS = [deliver_in_app]   # baad me: SMS / WhatsApp / email (generic template)


def _obsolete_reminder(event, moment: datetime) -> str | None:
    """Reminder abhi bhi sahi hai? Scheduler se abhi ki haalat. Galat ho to wajah, sahi ho to None.
    Scheduler na mile to HISError upar jaata hai: worker baad me dobara koshish karega."""
    p = json.loads(event["payload"])
    booking = his.get_his().find_for_patient(event["patient_ref"], event["record_ref"])
    if booking is None or booking.status != "confirmed":
        return "appointment cancelled"
    if (booking.date, booking.time) != (p["date"], p["time"]):
        return "appointment moved"
    if appointment_at(booking) <= moment:
        return "appointment time passed"
    return None


def process(event, moment: datetime) -> dict:
    """Ek event: (reminder ho to jaanch) -> har channel -> delivered. Galti par retry ka samay."""
    try:
        if event["event_type"] == "appointment.reminder":
            reason = _obsolete_reminder(event, moment)
            if reason:
                with db.connect() as conn:
                    db.finish_event(conn, event["event_id"], "skipped", reason)
                return {"event_id": event["event_id"], "status": "skipped", "reason": reason}
        results = [channel(event) for channel in CHANNELS]
    except Exception as e:  # noqa: BLE001  koi bhi asthayi galti: event khota nahin, baad me dobara
        attempts = event["attempts"]
        wait = timedelta(seconds=min(30 * 2 ** max(attempts - 1, 0), 3600))
        with db.connect() as conn:
            db.retry_event(conn, event["event_id"], _ts(moment + wait), f"{type(e).__name__}: {e}",
                           give_up=attempts >= MAX_ATTEMPTS)
        return {"event_id": event["event_id"], "status": "retry", "error": type(e).__name__}
    with db.connect() as conn:
        db.finish_event(conn, event["event_id"], "delivered")
    notification_id, created = results[0]
    return {"event_id": event["event_id"], "status": "delivered", "notification_id": notification_id,
            "created": created}


def run_once(moment: datetime | None = None, limit: int = 50) -> list[dict]:
    """Worker ka ek chakkar: jinka samay aa gaya unhe bhejo. Kai worker ek saath chalein to bhi har event ek ko."""
    moment = moment or common.now()
    with db.connect() as conn:
        events = db.claim_due_events(conn, _ts(moment), _ts(moment + LEASE), limit)
    return [process(event, moment) for event in events]


def replay(event_id: str, moment: datetime | None = None) -> dict:
    """Demo aur test: wahi event dobara chalao (jaise worker crash ke baad). Inbox me naya item nahin banna chahiye."""
    with db.connect() as conn:
        event = db.get_outbox_event(conn, event_id)
    if event is None:
        return {"status": "error", "message": "Event nahin mila."}
    return process(event, moment or common.now())


# ---------- patient API (web_app inhe bulata hai; har query login kiye patient tak simit) ----------

def link_for(destination: dict) -> str:
    return f"/?open={destination['view']}:{destination['id']}"


def view(row) -> dict:
    destination = json.loads(row["destination"])
    return {"id": row["id"], "event_type": row["event_type"], "created_at": row["created_at"],
            "read": row["read_at"] is not None,
            "title": {"hi": row["title_hi"], "en": row["title_en"]},
            "body": {"hi": row["body_hi"], "en": row["body_en"]},
            "destination": destination, "link": link_for(destination)}


def inbox(patient_ref: str) -> dict:
    with db.connect() as conn:
        rows = db.list_notifications(conn, patient_ref)
    items = [view(r) for r in rows]
    return {"notifications": items, "unread": sum(not i["read"] for i in items)}


def mark_read(patient_ref: str, notification_id: str) -> dict | None:
    with db.connect() as conn:
        row = db.mark_notification_read(conn, patient_ref, notification_id.strip().upper())
    return view(row) if row else None


def main() -> None:
    """Alag process ke roop me worker: `python -m hospital_agent.notifications` (har 3 second),
    ya `--once`, ya `--replay EVENT_ID` (dobara chala kar dikhana ki inbox me ek hi item)."""
    import argparse

    from dotenv import load_dotenv
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--replay")
    parser.add_argument("--interval", type=float, default=3.0)
    args = parser.parse_args()
    if args.replay:
        print(replay(args.replay))
        return
    while True:
        for result in run_once():
            print(result)
        if args.once:
            return
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
