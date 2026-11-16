"""Terminal me agent se baat karne ka demo.

    python run_demo.py

GOOGLE_API_KEY chahiye: use .env file me rakhein (dekhein .env.example).
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()  # .env ko agent import hone se PEHLE padhna zaroori hai (model ka naam wahin se aata hai)

from google.adk.events import Event, EventActions  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import DatabaseSessionService  # noqa: E402
from google.genai import types  # noqa: E402

from hospital_agent.agent import app, hospital_name  # noqa: E402
from hospital_agent.cards import cards_from_event, record_outcome  # noqa: E402
from hospital_agent.safety import EMERGENCY_LINE_EN, EMERGENCY_LINE_HI, detect_risk, risk_message  # noqa: E402
from hospital_agent.tools.actions import confirm_pending, discard_pending  # noqa: E402

APP_NAME = app.name
LANGUAGE_CHOICES = {"1": "Hindi", "2": "English"}
TEXT = {
    "Hindi": {
        "title": "हेल्प डेस्क: {hospital}",
        "card": "पुष्टि बाकी. c = पक्का करें, d = अनुरोध हटाएँ: ",
        "emergency": EMERGENCY_LINE_HI,
        "exit": "बंद करने के लिए 'exit' लिखें।",
        "you": "आप",
        "error": "अभी जवाब नहीं दे पा रहा। हेल्पडेस्क काउंटर से पूछें।",
        "no_key": "ध्यान दें: GOOGLE_API_KEY नहीं मिली। .env फ़ाइल बनाएँ; तब तक सिर्फ़ इमरजेंसी वाली जाँच चलेगी।",
    },
    "English": {
        "title": "Help desk: {hospital}",
        "card": "Confirmation pending. c = Confirm, d = Discard request: ",
        "emergency": EMERGENCY_LINE_EN,
        "exit": "Type 'exit' to quit.",
        "you": "You",
        "error": "Cannot answer right now. Please ask the helpdesk counter.",
        "no_key": "NOTE: GOOGLE_API_KEY not found. Create a .env file; until then only the emergency check works.",
    },
}
USER_ID = os.environ.get("DEMO_USER_ID", "patient_001")   # doosra patient: DEMO_USER_ID=patient_002
SESSION_ID = os.environ.get("DEMO_SESSION_ID", "demo_session")


def choose_language() -> str:
    """Shuru me bhasha ka menu. Lautata hai 'Hindi' ya 'English'."""
    print("Bhasha chunein / Choose language:")
    print("  1. हिंदी (देवनागरी)")
    print("  2. English")
    while True:
        choice = input("1 / 2: ").strip()
        if choice in LANGUAGE_CHOICES:
            return LANGUAGE_CHOICES[choice]
        print("Kripya 1 ya 2 likhein. / Please type 1 or 2.")


async def save_language(session_service, session, language: str) -> None:
    """Chuni hui bhasha session state me 'user:language' naam se rakhta hai.
    Saare agents ke instruction me {user:language?} isi se bharta hai."""
    event = Event(author="user", actions=EventActions(state_delta={"user:language": language}))
    await session_service.append_event(session, event)


async def ask_on_card(session_service, card: dict, text: dict) -> None:
    print("\n+---------- " + card["kind"].upper() + " ----------")
    for key, value in card["summary"].items():
        if key != "action":
            print(f"| {key:<14} {value}")
    print("+------------------------------")
    while True:
        choice = input(text["card"]).strip().lower()
        if choice in ("c", "d"):
            break
    if choice == "c":
        result = confirm_pending(card["action_id"], USER_ID, SESSION_ID, card["fingerprint"])
        while result.get("status") == "in_progress" and input(f"{result['message']} (r = retry): ").strip() == "r":
            result = confirm_pending(card["action_id"], USER_ID, SESSION_ID, card["fingerprint"])
    else:
        result = discard_pending(card["action_id"], USER_ID, SESSION_ID)
    print(f"=> {result}")
    session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    await record_outcome(session_service, session, card["kind"], "Confirm" if choice == "c" else "Discard", result)


async def main() -> None:
    session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///sessions.db")
    session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    if session is None:
        session = await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    runner = Runner(app=app, session_service=session_service)

    language = choose_language()
    await save_language(session_service, session, language)
    text = TEXT[language]

    print(text["title"].format(hospital=hospital_name()))
    print(text["emergency"])
    if not os.environ.get("GOOGLE_API_KEY"):
        print(text["no_key"])
    print(text["exit"])
    while True:
        user_text = input(f"\n{text['you']}: ").strip()
        if user_text.lower() in ("exit", "quit"):
            break
        risk = detect_risk(user_text)
        if risk:  # model, internet ya API key ke bina bhi yeh jawab milta hai
            print(f"help desk: {risk_message(risk, language)}")
            continue
        message = types.Content(role="user", parts=[types.Part(text=user_text)])
        cards = []
        try:
            async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=message):
                cards.extend(cards_from_event(event))
                if event.is_final_response() and event.content and event.content.parts:
                    print(f"{event.author}: {event.content.parts[0].text}")
            for card in cards:   # button jaisa: yeh jawab model ko nahin, seedha backend ko jaata hai
                await ask_on_card(session_service, card, text)
        except Exception as e:  # noqa: BLE001  demo: model na chale to bhi patient ko raasta mile
            print(f"help desk: {text['error']} ({type(e).__name__})")
            print(text["emergency"])


if __name__ == "__main__":
    asyncio.run(main())
