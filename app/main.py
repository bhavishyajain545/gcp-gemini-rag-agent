"""Cloud Run entrypoint: ADK FastAPI app with the built-in dev web UI enabled.

`adk web` does the same thing locally; this module exists so the container has
a single process (uvicorn) bound to $PORT.
"""

import os

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

AGENTS_DIR = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8080"))

app = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    web=True,
    allow_origins=["*"],
    bind_host="0.0.0.0",
    port=PORT,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
