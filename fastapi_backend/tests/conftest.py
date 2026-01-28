from __future__ import annotations

from dataclasses import dataclass
from typing import Generator, Optional

import pytest
from fastapi.testclient import TestClient

from tests.test_support.audit import InMemoryAuditLogRepository


@dataclass(frozen=True)
class Actor:
    """Simple actor representation for tests (user or service principal)."""

    actor_id: str
    actor_type: str = "user"  # "user" or "service"


@pytest.fixture()
def actor_publisher() -> Actor:
    """Publisher identity used for submission and validation calls."""
    return Actor(actor_id="user_publisher_1", actor_type="user")


@pytest.fixture()
def actor_approver() -> Actor:
    """Approver identity used for approval calls."""
    return Actor(actor_id="user_steward_1", actor_type="user")


@pytest.fixture()
def audit_repo() -> InMemoryAuditLogRepository:
    """
    In-memory audit repository.

    Tests assert that endpoints (once implemented) append events here for both success
    and failure outcomes.
    """
    return InMemoryAuditLogRepository()


@pytest.fixture()
def app(audit_repo: InMemoryAuditLogRepository):
    """
    Provides the FastAPI app under test.

    NOTE (TDD): The current codebase only exposes a minimal FastAPI app.
    These tests assume future implementation will:
      - register Data Product Publishing routes
      - write audit events to an audit repo exposed as `app.state.audit_log_repo`,
        or provide another DI hook that tests can override.

    If the app does not yet support this, tests will fail by design.
    """
    # Import the scaffold app (exists today).
    from src.api.main import app as fastapi_app  # type: ignore

    # Expected future DI pattern: app.state.audit_log_repo used by request handlers.
    # We set it here so handlers can write to it without external infrastructure.
    fastapi_app.state.audit_log_repo = audit_repo  # type: ignore[attr-defined]

    return fastapi_app


@pytest.fixture()
def client(app) -> Generator[TestClient, None, None]:
    """FastAPI test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth_headers(actor_publisher: Actor) -> dict:
    """
    Authorization header fixture.

    NOTE: Authentication/authorization is not implemented in the scaffold.
    These tests assume future handlers will read bearer token claims and map
    to actor_id/roles. For now this is a deterministic placeholder.
    """
    return {"Authorization": f"Bearer test-token-for-{actor_publisher.actor_id}"}


@pytest.fixture()
def approval_auth_headers(actor_approver: Actor) -> dict:
    """Authorization header fixture for an approver identity."""
    return {"Authorization": f"Bearer test-token-for-{actor_approver.actor_id}"}


@pytest.fixture()
def idempotency_key() -> str:
    """Deterministic idempotency key used in publish-critical operations (NFR-ERR-011)."""
    return "idem_test_key_001"


# PUBLIC_INTERFACE
def get_last_correlation_id_from_response(resp_json: dict) -> Optional[str]:
    """Return a correlation id from common response shapes (success or error)."""
    return resp_json.get("correlation_id") or resp_json.get("correlationId")
