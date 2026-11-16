import os

import uvicorn

from his_sandbox.app import create_app

if __name__ == "__main__":
    port = int(os.environ.get("HIS_SANDBOX_PORT", "8900"))
    print(f"HIS sandbox (synthetic data): http://127.0.0.1:{port}/docs")
    uvicorn.run(create_app(), host="127.0.0.1", port=port)
