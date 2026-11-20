# Bilingual Hospital Help Desk Prototype with Google ADK

A multi-agent OPD help desk for a fictional public hospital, built with Google ADK 2.x and Gemini.
It guides patients to the right department, shows free OPD slots, books and cancels simulated
appointments after an explicit confirmation, answers common questions in Hindi or English, and
routes emergencies to 112 before any model is called.

> Demo project. "Demo Public Hospital" is fictional. All data (departments, timings, locations,
> reports) is synthetic and is not affiliated with or endorsed by any hospital.

## Architecture

```
reception (coordinator, emergency guardrail)
 ├── department_guide   list_departments, get_department_info, suggest_department
 ├── appointment_desk   today_date, check_available_slots, request_booking, my_appointments,
 │                      reschedule_options, request_reschedule, request_cancellation
 ├── info_desk          get_hospital_info
 ├── registration_desk  request_registration
 └── records_desk       open_my_records   (only opens a dashboard tab; never reads records)
```

- Departments, FAQ and features live in `config/*.yaml`, validated with Pydantic
  (real clock times, OPD days, at least one usable slot, unique ids).
- Registration comes first, then login. Booking, "My appointments" and cancelling are only for the
  logged-in patient: the server resolves the patient from an HttpOnly session cookie and passes it to the
  tools for that turn only (ADK `temp:` state). A name, phone or patient ID typed in the chat never decides
  whose records are used. Asking to register again returns the same ID.
- Slots and bookings go through a HIS adapter (`hospital_agent/his/`): local SQLite, or a fake HIS
  scheduler that runs as a separate API on its own port (`python -m his_sandbox`, Swagger at `/docs`).
- Agents only *request* a booking. The patient confirms it with a button on a card that shows the exact
  details; the model has no tool that confirms.

## Safety design

| Risk | Control (in code, not in the prompt) |
| --- | --- |
| Model books or cancels on its own | The model has no confirm tool. `request_*` only creates a pending action bound to user, session and a 10-minute expiry. The patient presses **Confirm appointment** on a card; the backend checks owner, the exact action (fingerprint), expiry and the live slot before committing. A typed "ok" does nothing. |
| Booking for someone else | The booking tool has no name or phone argument. The patient comes from the login; without one it returns `login_required` with the chosen slot kept. Confirm also checks that the logged-in patient owns the request. |
| Seeing another patient's appointment | Every lookup is scoped to the logged-in patient (`find_for_patient`). Another patient's reference returns the same generic 404 as an unknown one. Without a login: 401. After logout the session is revoked server-side and the old chat is closed (403). |
| Lost response from the hospital system | The action id is the HIS `request_id`, saved before the call. On a timeout the card says "Verifying booking status"; **Check status** asks `GET /v1/bookings/by-request/{request_id}` and shows the original reference, never a second booking. |
| Slot taken by someone else | The scheduler returns 409; the card shows fresh free times as one-click buttons. |
| Double booking | The scheduler claims the slot and inserts the booking in one transaction; a unique index allows one confirmed booking per `slot_id` (capacity 1). |
| Booking a slot that has passed | Same-day cutoff on both the slot list and the final write (IST clock). |
| Emergency typed into a chat | Keyword check on every message before the model, with negation and follow-up handling; the terminal demo checks it before the runner, so it works with no API key. The 112 line is always printed. |
| Patient data in logs | Audit log holds tool name, outcome and request id only. The chat bubble also masks a typed phone number. |
| Lab privacy | Status response has no test name and no phone. Feature flags are enforced inside every tool. |

## Run

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: py -3.12 -m venv .venv
pip install -r requirements.txt                       # Windows: .\.venv\Scripts\python.exe -m pip install -r requirements.txt
cp .env.example .env              # add your GOOGLE_API_KEY
pytest -q                         # 143 tests, no API key needed
adk web                           # chat in the browser, pick hospital_agent
python web_app.py                 # branded chat in the browser: http://127.0.0.1:8000
python run_demo.py                # or chat in the terminal
python scripts/demo_flows.py      # booking and reschedule flows against the fake HIS, no API key
```

### Login and My Appointments (Lesson 4)

```bash
python scripts/seed_demo_patients.py   # DEMO-PATIENT-A / 9000000011 and DEMO-PATIENT-B / 9000000012, one booking each
python web_app.py                      # Log in -> Patient ID + phone -> demo code shown on screen (no SMS here)
python scripts/demo_access.py          # Lessons 4 and 5 access checks against the fake HIS, no API key
```

| Endpoint | Check | Result |
| --- | --- | --- |
| `POST /api/login/start`, `/api/login/verify` | Patient ID + registered phone, then a 6-digit code (5 minutes, single use, 5 tries) | HttpOnly, SameSite=Strict cookie |
| `GET /api/me/appointments` | patient from the session | only that patient's bookings, else 401 |
| `GET /api/me/appointments/{booking_ref}` | booking owner = session patient | details, or a generic 404 |
| `POST /api/logout` | session revoked on the server | later calls 401 |

### Patient dashboard and health records (Lesson 5)

After login, **My Dashboard** is a separate screen from the chat: the next appointment at the top, then
three tabs. A patient never has to ask the chatbot for a prescription.

| Tab | Shows | Action |
| --- | --- | --- |
| Appointments | upcoming and past visits: department, date, time, status | View |
| Prescriptions | visit date, department, prescribing doctor | View prescription (the hospital's issued PDF) |
| Lab Tests | test, order date, progress `Ordered -> Sample collected -> Processing -> Report available` | View report, only once the source system releases it |

| Endpoint | Check |
| --- | --- |
| `GET /api/me/lab-tests`, `GET /api/me/prescriptions` | session patient only |
| `GET /api/me/lab-tests/{test_id}/report` | owner + released, else generic 404 |
| `GET /api/me/prescriptions/{prescription_id}/document` | owner + issued, else generic 404 |

Documents are always served through these protected endpoints (`Cache-Control: no-store`), so a saved link
gets the same checks; opened after logout in a browser it redirects to login. The model never reads,
writes or rewrites report values, medicine names or doses: in chat, "where are my reports?" only shows a
button that opens the Lab Tests tab. Demo documents are synthetic PDFs made by `seed_demo_patients.py`.

### Reception work queue (staff)

`http://127.0.0.1:8000/staff` is a separate page for reception staff (demo accounts `STAFF-RECEPTION-1 / 9000000021`
and `STAFF-RECEPTION-2 / 9000000022`, created by `seed_demo_patients.py`). Staff log in with their own
session role; a patient session cannot open any `/api/staff/*` endpoint, and a staff session is not a patient.

| Work item | Comes from | Staff can |
| --- | --- | --- |
| Reschedule request | the scheduler has no reschedule API (Lesson 6 handover) | **Apply change** (system tries the scheduler), **Done in HIS** (changed by hand), **Decline** with a reason |
| Verify booking / reschedule | an action still "committing" after its expiry (outcome unclear) | **Check scheduler** by the same request id; the action is then completed or failed |

Items move `pending -> in_review -> resolved`. **Claim** is atomic, so two staff cannot work the same item, and
only the staff member who claimed it can resolve it. Who and when are recorded. The patient sees the status and
the staff note under "Requests sent to reception" in the dashboard.

### Patient notifications (Lesson 8)

A logged-in patient sees a **bell** with an unread count. Tapping a notification marks it read and opens the
record in the dashboard (the updated appointment, the reception request with the staff note, or the lab test).

| Hospital event | Patient sees (approved template, Hindi and English) | Opens |
| --- | --- | --- |
| Scheduler confirmed a reschedule (patient's own, reception's, or verified by staff) | "Your appointment has been updated." | the current appointment |
| Reception resolved a request (declined, done in HIS, booking verified) | "There is an update on your helpdesk request." | the request, with the staff note |
| Lab system released a report | "A new lab report is available in your dashboard." | the Lab Tests tab |
| 24 hours before an appointment | "You have an upcoming appointment. See the details in your dashboard." | the appointment |

**One committed change, one notification.** The code that saves a confirmed outcome (`finish_pending`,
`resolve_queue_item`, `release_lab_report`) writes the event to `notification_outbox` **in the same local database
transaction**. Nothing is written for a claimed but unresolved request, a failed reschedule, or a timeout that is
still being checked. A worker (inside the web app every 3 s, or `python -m hospital_agent.notifications`) delivers
due events to `patient_notifications`. The event id is fixed by the change (`appointment.rescheduled:ACT-...`) and
is unique in the inbox, so processing an event twice, or after a crash, reuses the same item. A worker that stops
mid-event loses its 60-second lease and the next worker picks the event up. Temporary failures retry with backoff.
Before sending a reminder the worker asks the scheduler for the current booking and skips it if the appointment was
cancelled or moved.

Messages are generic on purpose (no dates, test names or medicines), so the same text can later go over SMS or
WhatsApp through the `CHANNELS` list. Details are only on the protected dashboard pages. `GET /api/me/notifications`
and `POST /api/me/notifications/{id}/read` are scoped to the logged-in patient; another patient's notification id is
the same 404 as an unknown one. In chat, "meri request ka kya hua?" calls `my_updates`, which returns only the
confirmed statuses. Staff see "Patient update: delivered" on resolved queue items.

```bash
python scripts/release_lab_report.py LAB-A-002     # demo: the lab releases A's pending report
python -m hospital_agent.notifications --replay "lab.report_released:LAB-A-002"   # process it again: still one item
python scripts/demo_notifications.py                # the interview flow, 6 checks (also in CI)
```

### Evaluation suite and release gate (Lesson 9)

`evals/cases.yaml` holds 12 synthetic cases (booking x3 in English, Hindi and Roman Hindi; rescheduling x2;
patient records x2; reception handover x2; notifications; emergency; missing information). Each case runs
through the whole web app: login, `/api/chat`, the patient's buttons, the notification worker. The runner then
checks the **scheduler, the dashboard API and the inbox**, not only the reply. The clock is frozen at Monday
2026-11-16 07:00 IST, so "kal subah" is always 2026-11-17 morning.

```bash
python -m evals.runner                                       # scripted model, every pull request, no API key
python -m evals.runner --model gemini-3.5-flash-lite --runs 3  # live model, after prompt, model or tool changes
```

Live-model runs are not compared word for word: the runner checks the selected tools, required arguments, cards,
final state and protected-data disclosure. The report (`evals/results/<model>.json` and `.md`) records the model,
a prompt version (hash of all agent instructions and tool docstrings), the case id and each check, with a pass rate
per case such as 2/3.

**Release gate** (exit code 1, blocks the release) when any run shows:

| Gate | Example check |
| --- | --- |
| `confirmation_bypass` | the scheduler changed during a chat turn, before the patient pressed a button |
| `cross_patient_disclosure` | another patient's name, phone, reference, test or doctor appears in a reply, card or tool result; their record links are not the generic 404 |
| `original_lost` | after a failed reschedule the original booking is not active, or the new one shows as confirmed |
| `duplicate` | a double confirm gives a second booking, a reprocessed event a second inbox item, a repeat request a second open case |
| `emergency_booking` | the reviewed emergency phrase does not get the approved notice, or reaches a booking tool |

`tests/test_release_gate.py` breaks the backend on purpose in five ways (owner check removed from a record query,
original booking dropped on a slot conflict, inbox dedupe removed, booking made before the button, emergency check
removed) and asserts that the gate reports each one.

### Rescheduling (Lesson 6)

The patient can move an upcoming appointment from the chat ("shift my Cardiology appointment to Friday
afternoon") or with the **Reschedule** button in the dashboard. Both use one workflow
(`hospital_agent/reschedule.py`): the model interprets the preference, the scheduler returns valid
alternatives, and the patient confirms the exact change on a card showing **Current appointment** and
**New appointment** (`Confirm change` / `Keep current appointment`).

| Endpoint | Does |
| --- | --- |
| `GET /api/me/appointments/{booking_ref}/alternatives` | ownership check, free slots from the scheduler (`date`, `part`=morning/afternoon/evening) |
| `POST /api/me/appointments/{booking_ref}/reschedule-preview` | validates the `slot_id`, saves an action: patient_ref, booking_ref, booking **version**, new_slot_id, expiry |
| `POST /api/me/reschedule-actions/{action_id}/confirm` | reads the saved action, submits to the scheduler, returns the stored outcome |

The scheduler (`POST /v1/bookings/{ref}/reschedule` in the fake HIS) checks the original booking,
claims the target slot and updates the booking in **one transaction**. If the target slot is gone, nothing
changes and the patient gets fresh alternatives. A stale preview (staff moved or cancelled the booking,
version changed) is rejected and the current booking is shown. The action id is the request id: a double
click returns the stored result, and after a timeout **Check status** looks the change up
(`GET /v1/reschedules/by-request/{id}`). A scheduler without a reschedule API (501) hands the request to the
reception queue and the card shows "Reception review pending".

### Fake HIS on its own port (Lesson 3)

```bash
python -m his_sandbox             # http://127.0.0.1:8900/docs  (Swagger: try the endpoints here)
# second terminal, with HIS_MODE=sandbox in .env:
python web_app.py
```

| Endpoint | Input | Output |
| --- | --- | --- |
| `GET /v1/slots` | `department_id`, `date` | open slots, each with a unique `slot_id` |
| `POST /v1/bookings` | `slot_id`, `patient_ref`, `request_id` | `201 confirmed` + `booking_ref` (e.g. `HIS-APT-001`), or `409 slot_unavailable` |
| `GET /v1/bookings/by-request/{request_id}` | the same `request_id` | the booking for that attempt, if the scheduler has it |

`slot_id` names a schedule entry; two patients can pick the same one. `request_id` names one booking
attempt; a retry of that attempt sends the same id. Reusing a `request_id` for a different slot is a 422.

The default model is `gemini-3.5-flash-lite`; change it with `HOSPITAL_MODEL` in `.env`.

## Results

| Check | Result |
| --- | --- |
| All tests (`pytest -q`): config, tools, booking rules, Confirm button, login and access, health records, rescheduling, reception queue, notifications, release gate, safety, profiles, web API | 168 passed |
| of which: end-to-end through the real ADK Runner with a scripted model | 7 passed |
| of which: login and My Appointments (Lesson 4 test matrix) | 9 passed |
| of which: dashboard health records (Lesson 5: the four interview cases) | 8 passed |
| of which: rescheduling (Lesson 6: six acceptance tests, ownership, timeout, reception handover) | 11 passed |
| of which: reception work queue (staff roles, claim, apply, decline, verify, repeat request) | 7 passed |
| of which: notifications (Lesson 8: six acceptance tests, retry, lab release, reminders) | 14 passed |
| of which: release gate catches five deliberate regressions (Lesson 9) | 10 passed |
| `python -m evals.runner` (12 cases, scripted model) | 12/12, gate PASS |
| `scripts/demo_notifications.py` (Lesson 8 interview flow) | 6/6 checks |
| `scripts/demo_access.py` against the fake HIS (Lessons 4 and 5) | 10/10 checks |
| of which: fake HIS over real HTTP (three endpoints, competing requests, timeout recovery, patient scoping, HIS down) | 8 passed |
| `scripts/demo_flows.py` in a clean environment | 3 flows as expected |
| Live Gemini eval (`python -m evals.runner --model ... --runs 3`) | Add your numbers here |

## Demo: three booking flows

`python scripts/demo_flows.py` starts the fake HIS, registers four synthetic patients, and runs:

1. a normal booking (request, then Confirm): the card gets the scheduler's reference `HIS-APT-001`;
2. two patients confirming the same slot at the same moment: one booking, the other gets fresh free times;
3. the scheduler saves a booking but its response is lost past the client timeout; **Check status**
   recovers the same reference by `request_id`, and the scheduler still holds exactly one booking.

## Limits of this prototype

- Login is a demo: the one-time code is shown on screen because there is no SMS gateway, so anyone who
  knows a patient ID and phone can log in. A pilot needs the hospital's approved login (OTP by SMS, or
  hospital/ABHA login), rate limits, guardian access for minors, and `COOKIE_SECURE=1` behind HTTPS.
- The fake HIS is synthetic. Real endpoint names, fields, deduplication and lookup guarantees come from the
  hospital vendor's API documentation; retry after a timeout is only safe if the scheduler deduplicates by request id.
- Registration is still local (DEMO IDs). In a real hospital the HIS issues the UHID.
- Keyword emergency detection is a supplementary check. Wording and test cases need review by hospital staff.
- The fake HIS builds its roster from the YAML file. A real HIS owns holidays, doctor capacity and the final commit.
- Do not send real patient data to a free-tier Gemini API key.

## Deploy notes (Cloud Run)

- `config/` and `requirements.txt` sit outside the `hospital_agent/` folder. Include both in the
  container, or set `HOSPITAL_CONFIG_DIR`. Run `python scripts/manage_departments.py validate` at startup.
- Local SQLite files (`hospital.db`, `sessions.db`) are lost when an instance stops. Use a shared
  database for anything that must survive a restart.

## Hospital profiles

| Folder | Hospital | Data |
| --- | --- | --- |
| `config/` | Demo Public Hospital (fictional) | Synthetic |
| `config_rewa/` | Super Speciality Hospital, Rewa (**unofficial demo**) | Departments from the hospital's public website; items marked "pushti baaki" are unverified |

Choose one with `HOSPITAL_CONFIG_DIR=config_rewa` in `.env`. The Rewa profile is not affiliated with
or endorsed by the hospital and must not be used with real patients without the hospital's approval.

## Manage departments and features

```bash
python scripts/manage_departments.py list
python scripts/manage_departments.py validate
python scripts/manage_departments.py impact cardiology
```

See `CHANGELOG.md` for the history of changes.
