"""Mock service-status tool.

Stands in for a real status API or Cloud Monitoring uptime checks so the demo
is deterministic. Swap the body for a Monitoring API call without changing the
tool signature.
"""

from __future__ import annotations

from datetime import datetime, timezone

_SERVICES: dict[str, dict] = {
    "couchdb": {"status": "degraded", "latency_ms": 840, "note": "replication lag on node-2 after unclean restart"},
    "api-gateway": {"status": "healthy", "latency_ms": 42, "note": ""},
    "web-frontend": {"status": "healthy", "latency_ms": 118, "note": ""},
    "postgres": {"status": "healthy", "latency_ms": 9, "note": ""},
    "queue-processor": {"status": "down", "latency_ms": None, "note": "container restart loop since 09:12 UTC"},
}


def get_service_status(service: str) -> dict:
    """Get the current health of a platform service.

    Args:
        service: Service name, e.g. "couchdb", "api-gateway", "web-frontend", "postgres", "queue-processor".

    Returns:
        dict with `service`, `status` (healthy|degraded|down), `latency_ms`, `note`, `checked_at`;
        or `error` with the list of known services.
    """
    key = service.strip().lower()
    if key not in _SERVICES:
        return {"error": f"unknown service '{service}'", "known_services": sorted(_SERVICES)}
    return {"service": key, **_SERVICES[key], "checked_at": datetime.now(timezone.utc).isoformat()}
