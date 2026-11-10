"""Smoke test: run the agent programmatically with the ADK Runner.

    cd app && python test_agent.py "CouchDB crashed on prod, what are the recovery steps?"

Needs GOOGLE_GENAI_USE_VERTEXAI=TRUE, GOOGLE_CLOUD_PROJECT and
GOOGLE_CLOUD_LOCATION in the environment (same as Cloud Run). Firestore calls
need a Firestore database in the project.
"""

import asyncio
import sys

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from ops_agent.agent import root_agent


async def main(prompt: str) -> None:
    sessions = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name="ops_agent", session_service=sessions)
    session = await sessions.create_session(app_name="ops_agent", user_id="dev")

    async for event in runner.run_async(
        user_id="dev",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for part in (event.content.parts if event.content else []):
            if part.function_call:
                print(f"[tool call] {part.function_call.name}({dict(part.function_call.args or {})})")
            elif part.function_response:
                print(f"[tool result] {part.function_response.name}: {str(part.function_response.response)[:160]}...")
            elif part.text and event.is_final_response():
                print("\n" + part.text)


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "How do I safely recover CouchDB after a crash?"))
