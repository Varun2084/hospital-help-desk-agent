"""Terminal me agent se baat karne ka demo.

    python run_demo.py

GOOGLE_API_KEY chahiye: use .env file me rakhein (dekhein .env.example).
"""

import asyncio
import os

from dotenv import load_dotenv

load_dotenv()  # .env ko agent import hone se PEHLE padhna zaroori hai (model ka naam wahin se aata hai)

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import DatabaseSessionService  # noqa: E402
from google.genai import types  # noqa: E402

from hospital_agent.agent import root_agent  # noqa: E402
from hospital_agent.safety import EMERGENCY_LINE, detect_risk, risk_message  # noqa: E402

APP_NAME = "hospital_help_desk"
USER_ID = os.environ.get("DEMO_USER_ID", "patient_001")   # doosra patient: DEMO_USER_ID=patient_002
SESSION_ID = os.environ.get("DEMO_SESSION_ID", "demo_session")


async def main() -> None:
    session_service = DatabaseSessionService(db_url="sqlite+aiosqlite:///sessions.db")
    session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    if session is None:
        await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)

    print("Demo Public Hospital help desk (kalpanik hospital, demo data).")
    print(EMERGENCY_LINE)
    if not os.environ.get("GOOGLE_API_KEY"):
        print("DHYAN: GOOGLE_API_KEY nahin mili. .env file banayein (dekhein .env.example); tab tak sirf "
              "emergency wali jaanch chalegi.")
    print("Band karne ke liye 'exit' likhein.")
    while True:
        text = input("\nAap: ").strip()
        if text.lower() in ("exit", "quit"):
            break
        risk = detect_risk(text)
        if risk:  # model, internet ya API key ke bina bhi yeh jawab milta hai
            print(f"help desk: {risk_message(risk)}")
            continue
        message = types.Content(role="user", parts=[types.Part(text=text)])
        try:
            async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=message):
                if event.is_final_response() and event.content and event.content.parts:
                    print(f"{event.author}: {event.content.parts[0].text}")
        except Exception as e:  # noqa: BLE001  demo: model na chale to bhi patient ko raasta mile
            print(f"help desk: Abhi jawab nahin de pa raha ({type(e).__name__}). Helpdesk counter se puchhein.")
            print(EMERGENCY_LINE)


if __name__ == "__main__":
    asyncio.run(main())
