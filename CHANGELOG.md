# Changelog

Har badlaav yahan likhein: kya badla, kyun, aur kaun se tests jode.

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
