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
 ├── appointment_desk   today_date, check_available_slots,
 │                      request_booking, request_cancellation, confirm_action
 ├── info_desk          get_hospital_info
 └── lab_desk           get_lab_report_status        (feature flag, off by default)
```

- Departments, FAQ and features live in `config/*.yaml`, validated with Pydantic
  (real clock times, OPD days, at least one usable slot, unique ids).
- Appointments live in SQLite behind `hospital_agent/db.py`.

## Safety design

| Risk | Control (in code, not in the prompt) |
| --- | --- |
| Model books or cancels on its own | Two steps. `request_*` only creates a pending action bound to user, session and a 10-minute expiry. `confirm_action` writes only if the patient said yes in a **new** message; the model cannot confirm in the same turn. Retries return the stored outcome. |
| Double booking | Dates are stored as `YYYY-MM-DD` only; partial unique index on (department, date, time); booking and action consumption happen in one transaction. |
| Booking a slot that has passed | Same-day cutoff on both the slot list and the final write (IST clock). |
| Emergency typed into a chat | Keyword check on every message before the model, with negation and follow-up handling; the terminal demo checks it before the runner, so it works with no API key. The 112 line is always printed. |
| Patient data in logs | Audit log holds tool name, outcome and request id only. |
| Lab privacy | Status response has no test name and no phone. Feature flags are enforced inside every tool. |

## Run

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: py -3.12 -m venv .venv
pip install -r requirements.txt                       # Windows: .\.venv\Scripts\python.exe -m pip install -r requirements.txt
cp .env.example .env              # add your GOOGLE_API_KEY
pytest -q                         # 60 tests, no API key needed
adk web                           # chat in the browser, pick hospital_agent
python run_demo.py                # or chat in the terminal
```

The default model is `gemini-3.5-flash-lite`; change it with `HOSPITAL_MODEL` in `.env`.

## Results

| Check | Result |
| --- | --- |
| Unit and flow tests (config, tools, booking rules, safety, feature wiring) | 58 passed |
| End-to-end booking through the real ADK Runner with a scripted model, no API key | 2 passed |
| Live Gemini conversation and eval set (`adk web`, `adk eval`) | Add your numbers here |

## Limits of this prototype

- Identity is not verified. A phone number typed into a chat is not proof of who the patient is.
  A real system needs OTP or hospital login, record-level access checks and guardian permissions.
- The "yes" check reads the patient's latest message. A real system should use a confirm button
  outside the model (ADK tool confirmation) plus the checks above.
- Keyword emergency detection is a supplementary check. Wording and test cases need review by hospital staff.
- Slots come from a YAML file. A real hospital system (HIS) owns holidays, doctor capacity and the final commit.
- Do not send real patient data to a free-tier Gemini API key.

## Deploy notes (Cloud Run)

- `config/` and `requirements.txt` sit outside the `hospital_agent/` folder. Include both in the
  container, or set `HOSPITAL_CONFIG_DIR`. Run `python scripts/manage_departments.py validate` at startup.
- Local SQLite files (`hospital.db`, `sessions.db`) are lost when an instance stops. Use a shared
  database for anything that must survive a restart.

## Manage departments and features

```bash
python scripts/manage_departments.py list
python scripts/manage_departments.py validate
python scripts/manage_departments.py impact cardiology
```

See `CHANGELOG.md` for the history of changes.
