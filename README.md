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
 ├── appointment_desk   today_date, check_available_slots, request_booking, request_cancellation
 ├── info_desk          get_hospital_info
 ├── registration_desk  request_registration
 └── lab_desk           get_lab_report_status        (feature flag, off by default)
```

- Departments, FAQ and features live in `config/*.yaml`, validated with Pydantic
  (real clock times, OPD days, at least one usable slot, unique ids).
- Registration comes first: a booking is only for a registered patient (`patient_ref`, a DEMO patient ID).
  Asking to register again after a booking returns the same ID.
- Slots and bookings go through a HIS adapter (`hospital_agent/his/`): local SQLite, or a fake HIS
  scheduler that runs as a separate API on its own port (`python -m his_sandbox`, Swagger at `/docs`).
- Agents only *request* a booking. The patient confirms it with a button on a card that shows the exact
  details; the model has no tool that confirms.

## Safety design

| Risk | Control (in code, not in the prompt) |
| --- | --- |
| Model books or cancels on its own | The model has no confirm tool. `request_*` only creates a pending action bound to user, session and a 10-minute expiry. The patient presses **Confirm appointment** on a card; the backend checks owner, the exact action (fingerprint), expiry and the live slot before committing. A typed "ok" does nothing. |
| Booking for someone who is not registered | `request_booking` looks the patient up by phone and name (case and spaces ignored) and returns `not_registered`; the agent hands over to the registration desk. |
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
pytest -q                         # 112 tests, no API key needed
adk web                           # chat in the browser, pick hospital_agent
python web_app.py                 # branded chat in the browser: http://127.0.0.1:8000
python run_demo.py                # or chat in the terminal
python scripts/demo_flows.py      # three booking flows against the fake HIS, no API key
```

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
| All tests (`pytest -q`): config, tools, booking rules, Confirm button, safety, profiles, web API | 112 passed |
| of which: end-to-end through the real ADK Runner with a scripted model | 6 passed |
| of which: fake HIS over real HTTP (three endpoints, competing requests, timeout recovery, HIS down) | 7 passed |
| `scripts/demo_flows.py` in a clean environment | 3 flows as expected |
| Live Gemini conversation and eval set (`adk web`, `adk eval`) | Add your numbers here |

## Demo: three booking flows

`python scripts/demo_flows.py` starts the fake HIS, registers four synthetic patients, and runs:

1. a normal booking (request, then Confirm): the card gets the scheduler's reference `HIS-APT-001`;
2. two patients confirming the same slot at the same moment: one booking, the other gets fresh free times;
3. the scheduler saves a booking but its response is lost past the client timeout; **Check status**
   recovers the same reference by `request_id`, and the scheduler still holds exactly one booking.

## Limits of this prototype

- Identity is not verified. A phone number typed into a chat is not proof of who the patient is.
  A real system needs OTP or hospital login, record-level access checks and guardian permissions.
- The patient is identified by browser and session only. A real system must verify the patient
  (OTP, UHID or ABHA) before Confirm.
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
