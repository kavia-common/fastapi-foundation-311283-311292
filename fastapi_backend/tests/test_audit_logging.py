from __future__ import annotations

from datetime import datetime

import pytest

from tests.test_support.assertions import assert_audit_event_common_fields
from tests.test_support.audit import InMemoryAuditLogRepository


@pytest.mark.unit
def test_in_memory_audit_repo_appends_and_is_append_only():
    """
    NFR-AUD-001..004 (append-only intent), NFR-AUD-002 (required fields)
    GxP-A (audit readiness controls)

    This is a pure unit test for the test double used by API tests.
    """
    repo = InMemoryAuditLogRepository()
    ev1 = repo.append(
        event_type="DRAFT_SUBMITTED",
        actor_id="user1",
        correlation_id="corr1",
        outcome="SUCCESS",
        payload={"a": 1},
    )
    ev2 = repo.append(
        event_type="VALIDATION_RUN",
        actor_id="user1",
        correlation_id="corr1",
        outcome="FAILURE",
        reason="VAL_SCHEMA_VALIDATION_FAILED",
        payload={"b": 2},
    )

    events = repo.list_events()
    assert events == [ev1, ev2]

    assert_audit_event_common_fields(ev1)
    assert_audit_event_common_fields(ev2)

    assert ev1.payload_hash is not None
    assert ev2.payload_hash is not None
    assert ev2.reason == "VAL_SCHEMA_VALIDATION_FAILED"


@pytest.mark.unit
def test_audit_event_timestamp_is_datetime():
    """
    NFR-AUD-002 (timestamp_utc)
    """
    repo = InMemoryAuditLogRepository()
    ev = repo.append(
        event_type="PUBLISH",
        actor_id="svc_policy_engine",
        correlation_id="corr2",
        outcome="SUCCESS",
        payload={"decision": "PERMIT"},
    )
    assert isinstance(ev.timestamp_utc, datetime)
