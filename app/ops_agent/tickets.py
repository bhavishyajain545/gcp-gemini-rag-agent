"""Incident ticket tools backed by Firestore (native mode).

The Cloud Run service account only has `roles/datastore.user`, which is enough
for reads and writes on the `tickets` collection. No keys: the Firestore client
picks up the attached service account (or your ADC login locally).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from google.cloud import firestore

log = logging.getLogger(__name__)

COLLECTION = "tickets"
VALID_SEVERITIES = ("P1", "P2", "P3", "P4")

_db: firestore.Client | None = None


def _client() -> firestore.Client:
    global _db
    if _db is None:
        _db = firestore.Client(database=os.environ.get("FIRESTORE_DATABASE", "(default)"))
    return _db


def create_incident_ticket(title: str, severity: str, summary: str) -> dict:
    """Open a new incident ticket in the team's ticket store.

    Args:
        title: Short one-line title, e.g. "CouchDB crash on prod".
        severity: One of P1 (outage), P2 (major degradation), P3 (minor), P4 (low).
        summary: One paragraph describing impact, what was observed and what has been tried.

    Returns:
        dict with the new ticket `id`, `status` and the stored fields, or an `error`.
    """
    severity = severity.strip().upper()
    if severity not in VALID_SEVERITIES:
        return {"error": f"severity must be one of {', '.join(VALID_SEVERITIES)}"}
    if not title.strip() or not summary.strip():
        return {"error": "title and summary are required"}

    doc = {
        "title": title.strip(),
        "severity": severity,
        "summary": summary.strip(),
        "status": "open",
        "created_at": datetime.now(timezone.utc),
        "created_by": "ops-agent",
    }
    try:
        ref = _client().collection(COLLECTION).document()
        ref.set(doc)
    except Exception as exc:  # surface backend errors to the model instead of crashing the turn
        log.exception("create_incident_ticket failed")
        return {"error": f"ticket store unavailable: {type(exc).__name__}: {str(exc)[:200]}"}
    return {"id": ref.id, **{k: v for k, v in doc.items() if k != "created_at"}, "created_at": doc["created_at"].isoformat()}


def list_open_tickets() -> dict:
    """List incident tickets that are still open, newest first.

    Returns:
        dict with `count` and `tickets`: list of {id, title, severity, status, created_at}.
    """
    query = (
        _client()
        .collection(COLLECTION)
        .where(filter=firestore.FieldFilter("status", "==", "open"))
        .order_by("created_at", direction=firestore.Query.DESCENDING)
        .limit(20)
    )
    tickets = []
    try:
        for snap in query.stream():
            d = snap.to_dict() or {}
            created = d.get("created_at")
            tickets.append(
                {
                    "id": snap.id,
                    "title": d.get("title"),
                    "severity": d.get("severity"),
                    "status": d.get("status"),
                    "created_at": created.isoformat() if hasattr(created, "isoformat") else str(created),
                }
            )
    except Exception as exc:
        log.exception("list_open_tickets failed")
        return {"error": f"ticket store unavailable: {type(exc).__name__}: {str(exc)[:200]}"}
    return {"count": len(tickets), "tickets": tickets}
