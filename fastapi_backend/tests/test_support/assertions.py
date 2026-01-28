from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from tests.test_support.audit import AuditEvent, InMemoryAuditLogRepository


# PUBLIC_INTERFACE
def assert_standard_error_shape(body: Dict[str, Any]) -> None:
    """
    Assert the OpenAPI StandardError / GateFailureError required fields exist.

    OpenAPI components/schemas/StandardError requires:
      error_code, message, correlation_id, timestamp_utc, retryable
    """
    assert "error_code" in body and isinstance(body["error_code"], str) and body["error_code"]
    assert "message" in body and isinstance(body["message"], str) and body["message"]
    assert "correlation_id" in body and isinstance(body["correlation_id"], str) and body["correlation_id"]
    assert "timestamp_utc" in body and isinstance(body["timestamp_utc"], str) and body["timestamp_utc"]
    assert "retryable" in body and isinstance(body["retryable"], bool)


# PUBLIC_INTERFACE
def assert_audit_event_common_fields(event: AuditEvent) -> None:
    """Assert common audit fields are present and well-formed."""
    assert event.event_type and isinstance(event.event_type, str)
    assert event.actor_id and isinstance(event.actor_id, str)
    assert event.correlation_id and isinstance(event.correlation_id, str)
    assert event.outcome in {"SUCCESS", "FAILURE"}
    assert isinstance(event.timestamp_utc, datetime)


# PUBLIC_INTERFACE
def assert_audit_logged(
    repo: InMemoryAuditLogRepository,
    *,
    correlation_id: str,
    expected_event_type: Optional[str] = None,
    expected_outcome: Optional[str] = None,
    expected_reason: Optional[str] = None,
) -> AuditEvent:
    """
    Assert at least one audit event exists for the correlation id, and optionally matches
    event_type/outcome/reason.
    """
    events = repo.find_by_correlation_id(correlation_id)
    assert events, f"No audit events recorded for correlation_id={correlation_id}"

    ev = events[-1]
    assert_audit_event_common_fields(ev)

    if expected_event_type is not None:
        assert ev.event_type == expected_event_type
    if expected_outcome is not None:
        assert ev.outcome == expected_outcome
    if expected_reason is not None:
        assert ev.reason == expected_reason

    # Ensure at least some payload linkage exists (hash or reference)
    assert (ev.payload_hash is not None) or (ev.payload_ref is not None)

    return ev
