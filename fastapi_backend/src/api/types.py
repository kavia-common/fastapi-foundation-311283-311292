from __future__ import annotations

from typing import Any, Dict, Optional, Protocol


class AuditRepoProtocol(Protocol):
    """Protocol expected by the application for audit repositories."""

    def append(  # noqa: D401
        self,
        *,
        event_type: str,
        actor_id: str,
        correlation_id: str,
        outcome: str,
        reason: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        payload_ref: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Append an audit event and return the created event."""
        ...
