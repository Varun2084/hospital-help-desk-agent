# Changelog

Har badlaav yahan likhein: kya badla, kyun, aur kaun se tests jode.

## 0.11.0 (Lesson 5: Patient Dashboard aur Health Records)
- **Mera Dashboard / My Dashboard:** chat se alag screen. Upar Agli Appointment, phir teen tabs:
  Appointments (aane wali aur pichhli visit), Prescriptions (visit date, department, doctor, document),
  Lab Tests (Ordered -> Sample collected -> Processing -> Report available).
- **Status aur report alag:** status har stage par dikhta hai; "View report" sirf tab jab source system
  report ko patient ke liye release kare. Prescription read-only, hospital ka issued document.
- **Protected documents:** `GET /api/me/lab-tests`, `/api/me/lab-tests/{id}/report`, `/api/me/prescriptions`,
  `/api/me/prescriptions/{id}/document`. Har baar login + maalik + release/issue ki jaanch; doosre ka ya
  anjaan = wahi generic 404; `Cache-Control: no-store`. Logout ke baad saved link browser me khole to login.
- Model records nahin padhta ya likhta: purana `lab_desk` (report ID + phone lookup) hataya; naya
  `records_desk` sirf `open_my_records` se dashboard ka tab kholne ka button deta hai.
- Synthetic records aur PDFs `seed_demo_patients.py` me (A: ek processing test, ek released report, ek
  prescription; B: alag report aur prescription; dono ki ek pichhli visit). PDF bina extra library ke.
- `demo_access.py` me Lesson 5 ke checks (10/10). Tests me `.env` ka `HIS_MODE` ab asar nahin karta. Tests 123 se 126.

## 0.10.0 (Lesson 4: patient login aur My Appointments)
- **Login (authentication):** Patient ID + registered phone -> 6 ank ka code (5 minute, ek baar, 5 koshish).
  Demo me SMS nahin, isliye code screen par. Server-side session; browser ke paas sirf HttpOnly, SameSite=Strict
  cookie. Logout par session server par band.
- **Pehchaan server se:** web app har turn me login cookie se patient ID tools ko deta hai (ADK `temp:` state:
  sirf us turn ke liye, save nahin hota, model badal nahin sakta). `request_booking` me ab naam/phone ka argument
  hi nahin; bina login `login_required` aur chuna slot preview me. Confirm par bhi login wala patient = arzi ka patient.
- **My Appointments (authorization):** `GET /api/me/appointments` aur `/api/me/appointments/{booking_ref}`. Har
  query login wale patient tak simit (`find_for_patient`); doosre patient ka reference = wahi generic 404.
  Chat tool `my_appointments` bhi isi service se. HIS adapter aur Fake HIS me `list_for_patient`, `find_for_patient`.
- Login ke baad baat-cheet us patient ki; logout ya doosre login par purani chat band (403), UI nayi chat kholta hai.
- UI: Login / Logout, "My appointments" (list -> detail), login card (slot yaad), "Meri appointments" chip.
- `scripts/seed_demo_patients.py` (A aur B, ek-ek booking), `scripts/demo_access.py` (test matrix, CI me bhi).
- Terminal: `login` / `logout` command. Tests 112 se 123.

## 0.9.0 (pehle registration; Fake HIS ka slot_id / request_id contract)
- **Pehle registration, phir appointment:** `request_booking` naam + phone se registered patient dhoondhta hai
  (chhote-bade akshar aur space ka farq nahin). Na mile to `not_registered` aur agent registration desk ko bhejta
  hai. Booking patient ID (`patient_ref`) par hoti hai, card par "Patient ID" dikhta hai. Bug fix (screenshot):
  appointment ke baad registration maangne par naya registration ban jaata tha; ab wahi ID milti hai.
- **Fake HIS (Lesson 3):** alag port par (`python -m his_sandbox`, Swagger `/docs`). Teen endpoints:
  `GET /v1/slots` (har slot ka `slot_id`), `POST /v1/bookings` (`slot_id`, `patient_ref`, `request_id` ->
  `HIS-APT-001` ya 409), `GET /v1/bookings/by-request/{request_id}`. Slot claim + insert ek transaction me,
  `slot_id` par unique index (capacity 1). Slot ab HIS se aate hain; agent sirf "abhi ke baad" wali jaanch karta hai.
- Adapter (`his/base.py`, `local.py`, `http.py`, naya `slots.py`) isi contract par. Arzi ki id hi `request_id`;
  HIS ko bhejne se pehle `committing` me save.
- **Card:** slot chhin jaane par naye khaali samay ke button; timeout par "Verifying booking status" aur
  "Check status" button; recover hone par note. Chat bubble me likha phone number bhi masked.
- `app.js?v=0.9.0`: browser purani JavaScript cache se na chalaye.
- Demo flows synthetic patients se: pehle registration, phir teen flows. Tests 108 se 112.

## 0.8.0 (Confirm button aur HIS sandbox)
- **Confirm button:** model ab kuch pakka nahin kar sakta (`confirm_action` tool hata). Model sirf arzi banata hai;
  web app exact details ka card dikhata hai (hospital, department, tareekh, samay, "Confirmation pending") aur
  "Confirm appointment" / "Discard request" button. Backend jaanchta hai: arzi isi patient + session ki,
  card wali exact arzi (fingerprint), pending aur samay ke andar, phir HIS me slot ki taaza haalat. Terminal me
  bhi wahi, ek alag prompt se. Chat me "ok" / "haan" likhne se ab kuch nahin hota.
- Button ka nateeja session me likha jaata hai, taaki agle turn me agent ko pata ho.
- Bug fix: reception "Demo Public Hospital" bol raha tha jabki header me Rewa tha. Ab har agent ka hospital naam config se.
- **HIS adapter:** `hospital_agent/his/` (contract + LocalHIS + HttpHIS). Slot, booking aur cancel ab isi se.
  Arzi ki id = idempotency key. Timeout par `in_progress`; dobara Confirm par HIS se key se dhoondh kar wahi booking.
- **HIS sandbox:** `python -m his_sandbox` (FastAPI, synthetic data, fault injection).
- **Demo:** `python scripts/demo_flows.py`: normal booking, ek slot par do patient, timeout ke baad recovery.
- Purane `hospital.db` me naya column apne-aap judta hai. Tests 94 se 108.

## 0.7.2 (code cleanup, vyavhaar wahi)
- `confirm_action` apni file `tools/actions.py` me; booking, cancel aur registration ke `complete_*`
  functions ek `HANDLERS` table se bulaye jaate hain. Function ke andar ka import (circular import se bachav) hata.
- Saajhi cheezein (`now`, `today`, `error`, `PHONE_PATTERN`, `create_pending_action`) `tools/common.py` me,
  public naamon ke saath. Doosri file se `_` wale private naam import nahin hote.
- `registration.py` me beech ka `import json` upar; `tests/test_tools.py` me `import pytest` upar.
- Kuch "kya" batane wale comments hataye; "kyun" wale rakhe. Tests 94, sab pass.

## 0.7.0
- Naya feature `registration`: naye patient ka registration (naam, umar, gender, phone, shahar; 18 se kam
  ho to guardian). Booking jaisa do kadam ka flow; DEMO- patient ID. Aadhaar ya bimari ki jaankari nahin.
  Wahi naam + phone dobara aaye to wahi ID.
- `confirm_action` ab booking, cancel aur registration teeno sambhalta hai, aur har kaam ka feature flag jaanchta hai.
- Hospital profile: `config_rewa/` (Super Speciality Hospital, Rewa, UNOFFICIAL DEMO). Departments
  hospital ki public website se; anumaan wali baaton par "pushti baaki". `.env` me `HOSPITAL_CONFIG_DIR` se chunein.
- Browser app hospital ka naam aur disclaimer config se dikhata hai (`/api/info`).
- Tests 78 se 94: registration (12), profiles (3), web info (1).

## 0.6.1
- Bug fix: "रजिस्ट्रेशन कैसे करें?" ka jawab nahin milta tha, kyunki FAQ me sirf "पंजीकरण" tha.
  FAQ aur departments me Devanagari me likhe aam shabd jode (रजिस्ट्रेशन, कार्डियोलॉजी, एक्सरे...).
- info_desk aur department_guide ab tool ko patient ke shabd + ek chhota English shabd dete hain.
- 8 naye tests (Devanagari aur Roman sawaal). Tests 70 se 78.

## 0.6.0
- Browser app `web_app.py` (FastAPI, ADK ke saath pehle se install): logo, bhasha chunne ki screen, emergency patti,
  sujhaav wale buttons, desk ka naam har jawab par, mobile aur dark mode.
- Emergency browser me bhi model se pehle pakdi jaati hai. Doosre user ka session nahin khulta.
- `tests/test_web_app.py` (4 tests). Tests 66 se 70.

## 0.5.0
- Shuru me bhasha ka menu: 1. हिंदी (देवनागरी), 2. English. Chuni bhasha session state `user:language` me.
- Saare agents chuni hui bhasha me hi jawab dete hain; Hindi chuni ho to sirf Devanagari.
- Emergency aur self-harm ke tay sandesh bhi chuni hui bhasha me (model ke bina).
- `adk web` me bhasha na chuni ho to reception pehle bhasha poochhta hai.
- FAQ me radiology / X-ray ka jawab; info_desk ab X-ray, scan aur tests ke sawaal leta hai.
- `app = App(...)` jo `adk web` aur `run_demo.py` dono chalate hain. Tests 60 se 66.

## 0.4.0 (technical review ke baad)
- Booking/cancel ab do kadam me: `request_booking` / `request_cancellation` sirf arzi banate hain, `confirm_action`
  patient ke naye sandesh me 'haan' dekh kar hi likhta hai. Purane `book_appointment(confirmed=True)` aur
  `cancel_appointment` hata diye.
- Bug fix: tareekh sirf `YYYY-MM-DD`; '20261116' se booked slot dobara book ho jaata tha.
- Bug fix: usi din ke beete hue slot ab na dikhte hain, na book hote hain.
- Config: '09:75-26:99' jaise samay, khaali opd_days aur bina slot wali OPD ab reject.
- `suggest_department`: general_medicine na ho to crash ki jagah helpdesk.
- Emergency: "I cannot breathe" jaise vaakya jode; "accident follow-up" aur "no chest pain" ab booking nahin rokte.
- Privacy: audit log me sirf tool, nateeja, request id. Lab status se test ka naam aur phone hataya.
- Feature flag ab har tool ke andar bhi laagu (`feature_required`).
- FAQ me `verified_on` aur helpdesk; `run_demo.py` ab `.env` padhta hai aur emergency model se pehle jaanchta hai.
- Default model `gemini-3.5-flash-lite`. Tests 25 se 60.

## 0.3.1
- Bug fix: 'aaj' ki tareekh ab Bharat ke samay (Asia/Kolkata) se, server ke UTC se nahin. Windows ke liye `tzdata` joda.
- Code checker (ruff) ki saari shikayatein theek.

## 0.3.0
- Naya feature `lab_reports` (flag se band, testing ke baad chalu hoga).
- Test `test_every_feature_is_wired_everywhere`: har feature ka flag, tools aur agent ek saath hon.

## 0.2.0
- Bug fix: keyword ab poore shabd se milte hain ('heart' me 'ear' milne se ENT sujhaya ja raha tha).

## 0.1.0
- Reception agent, department guide, appointment desk, info desk.
- Emergency aur self-harm guardrail, phone masking, audit log.
