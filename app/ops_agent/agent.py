"""Root agent definition for the DevOps Ops Assistant.

ADK discovers `root_agent` from this module. The agent reasons with Gemini on
Vertex AI and calls plain Python functions as tools. Model names come from env
vars so the same code runs locally (`adk web`) and on Cloud Run.
"""

import os

from google.adk.agents import Agent
from google.genai import types

from .rag import read_runbook, search_runbooks
from .status import get_service_status
from .tickets import create_incident_ticket, list_open_tickets

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
# Gemini 3.x "thinks" before answering; for a tool-calling ops assistant a low
# thinking level keeps turns at a few seconds instead of tens of seconds.
THINKING_LEVEL = os.environ.get("GEMINI_THINKING_LEVEL", "low")

INSTRUCTION = """You are the on-call DevOps assistant for an internal platform team.

Your job:
1. Answer operational questions from the team's runbooks. For any how-to /
   recovery / procedure question: call `search_runbooks` exactly once, then call
   `read_runbook` on the best-matching source to get the full procedure, then
   answer using ONLY what that runbook says. Do not search repeatedly. Give the
   steps in order and cite the runbook file name as (source: <file>.md). If the
   runbooks do not cover the question, say so clearly instead of guessing.
2. Take actions when asked: open incident tickets with `create_incident_ticket`
   and list them with `list_open_tickets`. Before creating a ticket, make sure
   you have a title, a severity (P1-P4) and a one-paragraph summary; infer them
   from the conversation when obvious, otherwise ask one short question.
3. Report service health with `get_service_status` when asked about status,
   uptime or whether something is down.

Style: concise, numbered steps, no filler. Never invent commands that are not in
the runbooks. After creating a ticket, confirm its id and severity.
"""

root_agent = Agent(
    name="ops_agent",
    model=MODEL,
    description="DevOps on-call assistant: runbook RAG, incident tickets, service status.",
    instruction=INSTRUCTION,
    tools=[search_runbooks, read_runbook, create_incident_ticket, list_open_tickets, get_service_status],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.2,
        thinking_config=types.ThinkingConfig(thinking_level=THINKING_LEVEL) if THINKING_LEVEL != "off" else None,
    ),
)
