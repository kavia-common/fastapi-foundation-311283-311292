from __future__ import annotations

import pytest

from tests.test_support.assertions import assert_audit_logged, assert_standard_error_shape
from tests.test_support.factories import make_validation_run_request


@pytest.mark.parametrize(
    "gate_error_code, gate_name",
    [
        # FR-DPP-2005..2006, FR-DPP-3001..3003; NFR-ERR-001
        ("VAL_FRESHNESS_CHECK_FAILED", "FRESHNESS"),
        # FR-DPP-2002..2004
        ("VAL_SCHEMA_VALIDATION_FAILED", "SCHEMA"),
        # Requested by user instruction for parametrization (even if not explicitly in YAML examples)
        ("VAL_PII_SCAN_FAILED", "PII_SCAN"),
    ],
)
@pytest.mark.integration
def test_run_validation_gate_failure_returns_422_and_audits_failure(
    client,
    audit_repo,
    auth_headers,
    gate_error_code,
    gate_name,
):
    """
    NFR-ERR-001..002; NFR-AUD-002
    TP-DPP-NEG-001/002 + requested PII-scan variant

    OpenAPI: POST /drafts/{draft_id}/validations (operationId: runValidation)
      - 422: GateFailureError with stable error_code
    """
    draft_id = "dft_test_123"
    payload = make_validation_run_request(full_suite=True)

    # TDD note: Future implementation should allow deterministic injection of which gate fails.
    # The test expresses the expected API contract and audit behavior.
    resp = client.post(
        f"/drafts/{draft_id}/validations",
        json={**payload, "test_force_gate_failure": gate_name},
        headers=auth_headers,
    )

    assert resp.status_code == 422
    body = resp.json()
    assert_standard_error_shape(body)
    assert body["error_code"] == gate_error_code

    correlation_id = body["correlation_id"]

    # Audit: validation attempted, failed due to gate error code, with payload linkage.
    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="VALIDATION_RUN",
        expected_outcome="FAILURE",
        expected_reason=gate_error_code,
    )


@pytest.mark.integration
def test_run_validation_success_returns_200_or_202_and_audits_success(client, audit_repo, auth_headers):
    """
    FR-DPP-2001; FR-DPP-2010..2012; NFR-AUD-002
    (Happy path validation)

    OpenAPI: POST /drafts/{draft_id}/validations (operationId: runValidation)
      - 200: QualityReport (sync)
      - 202: ValidationRunAccepted (async)
    """
    draft_id = "dft_test_ok_001"
    payload = make_validation_run_request(full_suite=True)

    resp = client.post(
        f"/drafts/{draft_id}/validations",
        json={**payload, "test_force_gate_failure": None},
        headers=auth_headers,
    )

    assert resp.status_code in (200, 202)
    body = resp.json()

    # Both responses should include correlation_id in some form per design intent.
    # (OpenAPI explicitly includes it for 202 accepted; QualityReport itself doesn't,
    # but system should still provide correlation_id in response or headers.)
    correlation_id = body.get("correlation_id")
    assert correlation_id, "Expected correlation_id in response for traceability"

    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="VALIDATION_RUN",
        expected_outcome="SUCCESS",
    )
