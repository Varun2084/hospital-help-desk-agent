"""Browser me chalne wala chat app (FastAPI). Wahi agents, wahi tools, bas terminal ki jagah web page.

    python web_app.py          # phir browser me kholen: http://127.0.0.1:8000

GOOGLE_API_KEY .env file me honi chahiye (dekhein .env.example).
"""

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # .env ko agent import hone se PEHLE padhna zaroori hai

from fastapi import FastAPI, HTTPException, Request, Response  # noqa: E402
from fastapi.responses import FileResponse, RedirectResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from google.adk.events import Event, EventActions  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import DatabaseSessionService  # noqa: E402
from google.genai import types  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from hospital_agent import auth, db, his, notifications, reception, records, reschedule  # noqa: E402
from hospital_agent.agent import app as adk_app  # noqa: E402
from hospital_agent.cards import cards_from_event, record_outcome  # noqa: E402
from hospital_agent.config import load_hospital_info  # noqa: E402
from hospital_agent.safety import detect_risk, risk_message  # noqa: E402
from hospital_agent.tools.actions import confirm_pending, discard_pending  # noqa: E402
from hospital_agent.tools.appointments import appointment_view  # noqa: E402
from hospital_agent.tools.common import AUTH_KEY  # noqa: E402

STATIC_DIR = Path(__file__).parent / "static"
COOKIE = "opd_session"
STAFF_COOKIE = "opd_staff"   # staff ka alag cookie; role server par session me likha
OWNER_KEY = "session_owner"   # login ke baad yeh baat-cheet kis patient ki hai (server likhta hai)


def current_patient(request: Request):
    """Authentication: cookie ke token se server patient tay karta hai. Browser ka bheja user_id kabhi nahin."""
    return auth.patient_for_token(request.cookies.get(COOKIE))


def require_staff(request: Request):
    """Authorization: sirf staff session (role 'staff') aur role 'reception'. Patient cookie yahan kuch nahin kholta."""
    staff = auth.staff_for_token(request.cookies.get(STAFF_COOKIE))
    if staff is None:
        raise HTTPException(status_code=401, detail="Staff login required")
    if staff["role"] != "reception":
        raise HTTPException(status_code=403, detail="Reception role required")
    return staff


def require_patient(request: Request):
    patient = current_patient(request)
    if patient is None:
        raise HTTPException(status_code=401, detail="Login required")
    return patient


async def _notify_loop(interval: float | None = None) -> None:
    interval = interval or float(os.environ.get("NOTIFY_INTERVAL", "3"))
    while True:
        try:
            await run_in_threadpool(notifications.run_once)
        except Exception as e:  # noqa: BLE001  worker ruk na jaaye; event database me safe hain
            print(f"notification worker: {type(e).__name__}: {e}")
        await asyncio.sleep(interval)


def _kind(action_id: str) -> str:
    with db.connect() as conn:
        row = db.get_pending(conn, action_id.strip().upper())
    return row["kind"] if row else "request"

DESK_NAMES = {  # jawab dene wale desk ka naam, patient ki bhasha me
    "Hindi": {"reception": "रिसेप्शन", "department_guide": "विभाग मार्गदर्शन", "appointment_desk": "अपॉइंटमेंट डेस्क",
              "info_desk": "जानकारी डेस्क", "records_desk": "रिकॉर्ड डेस्क", "safety": "आपातकालीन सूचना",
              "registration_desk": "रजिस्ट्रेशन डेस्क"},
    "English": {"reception": "Reception", "department_guide": "Department guide",
                "appointment_desk": "Appointment desk", "info_desk": "Information desk", "records_desk": "Records desk",
                "safety": "Emergency notice", "registration_desk": "Registration desk"},
}


class StartRequest(BaseModel):
    language: str = Field(pattern="^(Hindi|English)$")
    user_id: str = Field(min_length=8, max_length=64, pattern="^[A-Za-z0-9_-]+$")


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=8, max_length=64, pattern="^[A-Za-z0-9_-]+$")
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class LoginStart(BaseModel):
    patient_id: str = Field(min_length=4, max_length=40)
    phone: str = Field(pattern=r"^[6-9]\d{9}$")


class StaffLoginStart(BaseModel):
    staff_id: str = Field(min_length=6, max_length=40)
    phone: str = Field(pattern=r"^[6-9]\d{9}$")


class StaffLoginVerify(BaseModel):
    staff_id: str = Field(min_length=6, max_length=40)
    code: str = Field(pattern=r"^\d{6}$")


class Resolve(BaseModel):
    decision: str = Field(pattern="^(apply|done_manually|decline|check)$")
    note: str = Field(default="", max_length=300)


class LoginVerify(BaseModel):
    patient_id: str = Field(min_length=4, max_length=40)
    code: str = Field(pattern=r"^\d{6}$")


class PreviewRequest(BaseModel):
    slot_id: str = Field(min_length=10, max_length=80)


class DashboardAction(BaseModel):
    fingerprint: str = Field(min_length=8, max_length=64)


class ActionRequest(BaseModel):
    user_id: str = Field(min_length=8, max_length=64, pattern="^[A-Za-z0-9_-]+$")
    session_id: str = Field(min_length=8, max_length=64)
    action_id: str = Field(min_length=4, max_length=32)
    fingerprint: str = Field(min_length=8, max_length=64)


def create_app(runner: Runner | None = None, session_service=None) -> FastAPI:
    """Web app banata hai. Tests apna runner aur session service de sakte hain."""
    session_service = session_service or DatabaseSessionService(db_url="sqlite+aiosqlite:///sessions.db")
    runner = runner or Runner(app=adk_app, session_service=session_service)
    app_name = runner.app_name

    @asynccontextmanager
    async def lifespan(_):
        """Notification worker app ke saath chalta hai (NOTIFY_WORKER=0 se band; tab alag process:
        python -m hospital_agent.notifications). Event database me hain, isliye restart par kuch nahin khota."""
        task = asyncio.create_task(_notify_loop()) if os.environ.get("NOTIFY_WORKER", "1") == "1" else None
        yield
        if task:
            task.cancel()

    web = FastAPI(title="OPD Sahayak", docs_url=None, redoc_url=None, lifespan=lifespan)

    @web.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @web.get("/staff")
    async def staff_page():
        return FileResponse(STATIC_DIR / "staff.html")

    # ---------- Reception work queue (staff) ----------
    @web.post("/api/staff/login/start")
    async def staff_login_start(req: StaffLoginStart):
        result = auth.start_staff_login(req.staff_id, req.phone)
        if result["status"] != "code_sent":
            raise HTTPException(status_code=400, detail=result["message"])
        return result

    @web.post("/api/staff/login/verify")
    async def staff_login_verify(req: StaffLoginVerify, response: Response):
        token = auth.verify_login(req.staff_id, req.code, role="staff")
        if token is None:
            raise HTTPException(status_code=400, detail="Code galat hai ya purana ho gaya.")
        response.set_cookie(STAFF_COOKIE, token, max_age=auth.SESSION_HOURS * 3600, httponly=True,
                            samesite="strict", secure=os.environ.get("COOKIE_SECURE") == "1")
        staff = auth.staff_for_token(token)
        return {"staff_id": staff["id"], "name": staff["name"], "role": staff["role"]}

    @web.post("/api/staff/logout")
    async def staff_logout(request: Request, response: Response):
        auth.logout(request.cookies.get(STAFF_COOKIE))
        response.delete_cookie(STAFF_COOKIE)
        return {"ok": True}

    @web.get("/api/staff/me")
    async def staff_me(request: Request):
        staff = require_staff(request)
        return {"staff_id": staff["id"], "name": staff["name"], "role": staff["role"]}

    @web.get("/api/staff/queue")
    async def staff_queue(request: Request, status: str = ""):
        require_staff(request)
        return {"items": await run_in_threadpool(reception.queue, status or None)}

    @web.post("/api/staff/queue/{item_id}/claim")
    async def staff_claim(item_id: str, request: Request):
        staff = require_staff(request)
        result = reception.claim(item_id, staff["id"])
        if result["status"] != "ok":
            raise HTTPException(status_code=409, detail=result["message"])
        return result

    @web.post("/api/staff/queue/{item_id}/resolve")
    async def staff_resolve(item_id: str, req: Resolve, request: Request):
        staff = require_staff(request)
        return await run_in_threadpool(reception.resolve, item_id, staff["id"], req.decision, req.note)

    @web.get("/api/me/requests")
    async def my_requests(request: Request):
        """Patient: apni requests ki sthiti (Reception review pending / hal)."""
        return {"requests": reception.requests_for_patient(require_patient(request)["id"])}

    # ---------- Notifications (Lesson 8): bell aur inbox, sirf apne ----------
    @web.get("/api/me/notifications")
    async def my_notifications(request: Request):
        return notifications.inbox(require_patient(request)["id"])

    @web.post("/api/me/notifications/{notification_id}/read")
    async def read_notification(notification_id: str, request: Request):
        item = notifications.mark_read(require_patient(request)["id"], notification_id)
        if item is None:   # anjaan ya doosre patient ki: ek jaisa jawab
            raise HTTPException(status_code=404, detail="Notification not found")
        return item

    @web.get("/api/me/requests/{item_id}")
    async def my_request(item_id: str, request: Request):
        """Notification se khulne wala request record (staff ka faisla aur agla kadam)."""
        mine = reception.requests_for_patient(require_patient(request)["id"])
        found = [r for r in mine if r["id"] == item_id.strip().upper()]
        if not found:
            raise HTTPException(status_code=404, detail="Request not found")
        return found[0]

    @web.get("/api/info")
    async def info():
        """Hospital ka naam aur disclaimer config se, taaki har hospital ka profile apna naam dikhaye."""
        hospital = load_hospital_info()
        return {"hospital_name": hospital.hospital_name, "disclaimer": " ".join(hospital.disclaimer.split())}

    # ---------- login (authentication) ----------
    @web.post("/api/login/start")
    async def login_start(req: LoginStart):
        result = auth.start_login(req.patient_id, req.phone)
        if result["status"] != "code_sent":
            raise HTTPException(status_code=400, detail=result["message"])
        return result

    @web.post("/api/login/verify")
    async def login_verify(req: LoginVerify, response: Response):
        token = auth.verify_login(req.patient_id, req.code)
        if token is None:
            raise HTTPException(status_code=400, detail="Code galat hai ya purana ho gaya.")
        response.set_cookie(COOKIE, token, max_age=auth.SESSION_HOURS * 3600, httponly=True, samesite="strict",
                            secure=os.environ.get("COOKIE_SECURE") == "1")
        patient = auth.patient_for_token(token)
        return {"patient_id": patient["id"], "name": patient["full_name"]}

    @web.post("/api/logout")
    async def logout(request: Request, response: Response):
        auth.logout(request.cookies.get(COOKIE))   # server par session band
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @web.get("/api/me")
    async def me(request: Request):
        patient = require_patient(request)
        return {"patient_id": patient["id"], "name": patient["full_name"]}

    # ---------- My Appointments (authorization: har query isi patient tak simit) ----------
    @web.get("/api/me/appointments")
    async def my_appointments(request: Request):
        patient = require_patient(request)
        try:
            bookings = await run_in_threadpool(his.get_his().list_for_patient, patient["id"])
        except his.HISError as e:
            raise HTTPException(status_code=503, detail="Hospital system not available") from e
        return {"appointments": [appointment_view(b) for b in bookings]}

    @web.get("/api/me/appointments/{booking_ref}")
    async def my_appointment(booking_ref: str, request: Request):
        patient = require_patient(request)
        try:
            booking = await run_in_threadpool(his.get_his().find_for_patient, patient["id"], booking_ref.upper())
        except his.HISError as e:
            raise HTTPException(status_code=503, detail="Hospital system not available") from e
        if booking is None:   # anjaan ya doosre patient ka: ek jaisa jawab, kuch disclose nahin
            raise HTTPException(status_code=404, detail="Appointment not found")
        return appointment_view(booking)

    # ---------- Reschedule (Lesson 6): dashboard aur chat ek hi workflow ----------
    @web.get("/api/me/appointments/{booking_ref}/alternatives")
    async def reschedule_alternatives(booking_ref: str, request: Request, date: str = "", part: str = "any"):
        patient = require_patient(request)
        result = await run_in_threadpool(reschedule.alternatives, patient["id"], booking_ref, date, part)
        if result["status"] == "error" and result["message"] == reschedule.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Appointment not found")
        return result

    @web.post("/api/me/appointments/{booking_ref}/reschedule-preview")
    async def reschedule_preview(booking_ref: str, req: PreviewRequest, request: Request):
        """Chuna slot jaanch kar arzi (preview). Appointment abhi nahin badalti."""
        patient = require_patient(request)
        result = await run_in_threadpool(reschedule.create_preview, patient["id"], booking_ref, req.slot_id,
                                         *reschedule.dashboard_owner(patient["id"]))
        if result["status"] == "error" and result["message"] == reschedule.NOT_FOUND:
            raise HTTPException(status_code=404, detail="Appointment not found")
        if result["status"] != "needs_confirmation":
            raise HTTPException(status_code=409, detail=result["message"])
        return {k: result[k] for k in ("action_id", "kind", "summary", "expires_at", "fingerprint")}

    @web.post("/api/me/reschedule-actions/{action_id}/confirm")
    async def reschedule_confirm(action_id: str, req: DashboardAction, request: Request):
        """Confirm change: values saved arzi se (patient, booking, version, naya slot); browser se sirf fingerprint."""
        patient = require_patient(request)
        user_id, session_id, _ = reschedule.dashboard_owner(patient["id"])
        return {"result": await run_in_threadpool(confirm_pending, action_id, user_id, session_id, req.fingerprint,
                                                  patient["id"])}

    @web.post("/api/me/reschedule-actions/{action_id}/discard")
    async def reschedule_keep(action_id: str, request: Request):
        """Keep current appointment: sirf preview hatata hai."""
        patient = require_patient(request)
        user_id, session_id, _ = reschedule.dashboard_owner(patient["id"])
        return {"result": await run_in_threadpool(discard_pending, action_id, user_id, session_id)}

    # ---------- Health records (Lesson 5): list + protected documents ----------
    def _document(request: Request, pdf_for, record_id: str, filename: str):
        """Document hamesha isi protected raaste se: har baar login, maalik aur release/issue ki jaanch."""
        patient = current_patient(request)
        if patient is None:
            if "text/html" in request.headers.get("accept", ""):   # browser me khola gaya saved link
                return RedirectResponse("/?login=1", status_code=303)
            raise HTTPException(status_code=401, detail="Login required")
        pdf = pdf_for(patient["id"], record_id)
        if pdf is None:   # anjaan, doosre patient ka, ya abhi release nahin: ek hi jawab
            raise HTTPException(status_code=404, detail="Document not found")
        return Response(pdf, media_type="application/pdf", headers={
            "Content-Disposition": f'inline; filename="{filename}"', "Cache-Control": "no-store, private",
            "X-Content-Type-Options": "nosniff"})

    @web.get("/api/me/lab-tests")
    async def my_lab_tests(request: Request):
        return {"lab_tests": records.lab_tests_for(require_patient(request)["id"])}

    @web.get("/api/me/lab-tests/{test_id}/report")
    async def my_lab_report(test_id: str, request: Request):
        return _document(request, records.lab_report_pdf, test_id, "lab-report.pdf")

    @web.get("/api/me/prescriptions")
    async def my_prescriptions(request: Request):
        return {"prescriptions": records.prescriptions_for(require_patient(request)["id"])}

    @web.get("/api/me/prescriptions/{prescription_id}/document")
    async def my_prescription(prescription_id: str, request: Request):
        return _document(request, records.prescription_pdf, prescription_id, "prescription.pdf")

    @web.post("/api/start")
    async def start(req: StartRequest):
        """Nayi baat-cheet: session banata hai aur chuni hui bhasha state me rakhta hai."""
        session = await session_service.create_session(
            app_name=app_name, user_id=req.user_id, session_id="web-" + uuid.uuid4().hex[:12])
        event = Event(author="user", actions=EventActions(state_delta={"user:language": req.language}))
        await session_service.append_event(session, event)
        return {"session_id": session.id, "language": req.language}

    @web.post("/api/chat")
    async def chat(req: ChatRequest, request: Request):
        session = await session_service.get_session(
            app_name=app_name, user_id=req.user_id, session_id=req.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session nahin mila. Nayi baat-cheet shuru karein.")
        language = session.state.get("user:language", "English")
        names = DESK_NAMES[language]

        risk = detect_risk(req.message)
        if risk:  # model, internet ya API key ke bina bhi yeh jawab milta hai
            return {"replies": [{"desk": names["safety"], "text": risk_message(risk, language),
                                 "kind": "emergency"}]}

        patient = current_patient(request)
        owner = session.state.get(OWNER_KEY)
        if owner and (patient is None or patient["id"] != owner):   # kisi aur login ki baat-cheet
            raise HTTPException(status_code=403, detail="Nayi baat-cheet shuru karein.")
        state_delta = {AUTH_KEY: patient["id"]} if patient else None   # sirf is turn ke liye
        if patient and not owner:
            state_delta[OWNER_KEY] = patient["id"]
        message = types.Content(role="user", parts=[types.Part(text=req.message)])
        replies, cards = [], []
        try:
            async for event in runner.run_async(user_id=req.user_id, session_id=req.session_id,
                                                new_message=message, state_delta=state_delta):
                cards.extend(cards_from_event(event))   # Confirm card (model ki arzi)
                if event.is_final_response() and event.content and event.content.parts:
                    text = "".join(p.text or "" for p in event.content.parts).strip()
                    if text:
                        replies.append({"desk": names.get(event.author, event.author), "text": text,
                                        "kind": "agent"})
        except Exception as e:  # noqa: BLE001  model na chale to bhi patient ko raasta mile
            fallback = {"Hindi": "अभी जवाब नहीं दे पा रहा। कृपया हेल्पडेस्क काउंटर से पूछें। इमरजेंसी में 112 पर कॉल करें।",
                        "English": "Cannot answer right now. Please ask the helpdesk counter. "
                                   "In an emergency, call 112."}[language]
            return {"replies": [{"desk": names["reception"], "text": fallback, "kind": "error"}],
                    "error": type(e).__name__}
        return {"replies": replies, "cards": cards}

    async def _own_session(req: ActionRequest):  # baat-cheet isi browser ki ho
        session = await session_service.get_session(
            app_name=app_name, user_id=req.user_id, session_id=req.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Session nahin mila.")
        return session

    @web.post("/api/actions/confirm")
    async def confirm(req: ActionRequest, request: Request):
        """Confirm appointment button. Model is raaste me nahin hai: backend khud jaanch kar commit karta hai.
        Booking/cancel ki arzi par login kiya hua patient wahi hona chahiye jiske naam par arzi bani."""
        session = await _own_session(req)
        patient = current_patient(request)
        result = await run_in_threadpool(confirm_pending, req.action_id, req.user_id, req.session_id,
                                         req.fingerprint, patient["id"] if patient else None)
        await record_outcome(session_service, session, _kind(req.action_id), "Confirm", result)
        return {"result": result}

    @web.post("/api/actions/discard")
    async def discard(req: ActionRequest):
        """Discard request button: sirf draft hatata hai."""
        session = await _own_session(req)
        result = await run_in_threadpool(discard_pending, req.action_id, req.user_id, req.session_id)
        await record_outcome(session_service, session, _kind(req.action_id), "Discard", result)
        return {"result": result}

    web.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return web


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print(f"Browser me kholen: http://127.0.0.1:{port}")
    uvicorn.run(create_app(), host="127.0.0.1", port=port)
