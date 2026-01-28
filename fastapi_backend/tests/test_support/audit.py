from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AuditEvent:
    """
    Audit event model for tests.

    This mirrors the design intent in:
      - `python-class-definitions.md` (AuditLog.append_event)
    And asserts fields required by audit readiness expectations.
    """

    event_type: str
    actor_id: str
    timestamp_utc: datetime
    correlation_id: str
    outcome: str  # "SUCCESS" or "FAILURE"
    reason: Optional[str] = None  # error_code or failure reason
    payload_hash: Optional[str] = None
    payload_ref: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


class InMemoryAuditLogRepository:
    """In-memory append-only audit repository for tests."""

    def __init__(self) -> None:
        self._events: List[AuditEvent] = []

    # PUBLIC_INTERFACE
    def append(
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
        timestamp_utc: Optional[datetime] = None,
    ) -> AuditEvent:
        """
        Append a new audit event.

        Tests treat audit logging as compliance-critical; future implementation should
        fail closed when audit append fails for regulated operations.
        """
        if timestamp_utc is None:
            timestamp_utc = datetime.now(timezone.utc)

        payload_hash = None
        if payload is not None:
            payload_hash = sha256_canonical_json(payload)

        ev = AuditEvent(
            event_type=event_type,
            actor_id=actor_id,
            timestamp_utc=timestamp_utc,
            correlation_id=correlation_id,
            outcome=outcome,
            reason=reason,
            payload_hash=payload_hash,
            payload_ref=payload_ref,
            details=details or {},
        )
        self._events.append(ev)
        return ev

    # PUBLIC_INTERFACE
    def list_events(self) -> List[AuditEvent]:
        """Return all audit events in append order."""
        return list(self._events)

    # PUBLIC_INTERFACE
    def last_event(self) -> Optional[AuditEvent]:
        """Return the most recent audit event, if any."""
        return self._events[-1] if self._events else None

    # PUBLIC_INTERFACE
    def find_by_correlation_id(self, correlation_id: str) -> List[AuditEvent]:
        """Return all events that match the given correlation_id."""
        return [e for e in self._events if e.correlation_id == correlation_id]


def _stable_json_default(obj: Any) -> Any:
    """
    JSON serializer fallback that is deterministic and bytes-safe.

    - bytes/bytearray: decode UTF-8 with replacement (stable) for canonicalization
      (note: for *hashing*, bytes are handled specially in sha256_canonical_json).
    """
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


# PUBLIC_INTERFACE
def sha256_canonical_json(payload: Any) -> str:
    """
    Compute SHA-256 of canonical JSON for stable hashing across runs.

    Robustness requirements (tests):
    - Must not raise TypeError when payload (or nested values) contains bytes.
    - If payload itself is bytes/bytearray, hash raw bytes directly.
    """
    if isinstance(payload, (bytes, bytearray)):
        return hashlib.sha256(bytes(payload)).hexdigest()

    # Ensure determinism: sort keys, compact separators.
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_stable_json_default,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
