"""Fake HIS ko alag port par chalayein:

    python -m his_sandbox        # Swagger: http://127.0.0.1:8900/docs

Kaun sa hospital profile (slots ka roster), .env ka HOSPITAL_CONFIG_DIR tay karta hai.
"""

import os

from dotenv import load_dotenv

load_dotenv()  # roster ke liye HOSPITAL_CONFIG_DIR; app import se pehle

import uvicorn  # noqa: E402

from his_sandbox.app import create_app  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("HIS_SANDBOX_PORT", "8900"))
    print(f"Fake HIS (synthetic data): http://127.0.0.1:{port}/docs")
    uvicorn.run(create_app(), host="127.0.0.1", port=port)
