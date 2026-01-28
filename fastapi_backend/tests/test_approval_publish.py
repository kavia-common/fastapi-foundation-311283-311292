from __future__ import annotations

import pytest

from tests.test_support.assertions import assert_audit_logged, assert_standard_error_shape
from tests.test_support.factories import make_approval_decision_request, make_publish_request


@pytest.mark.integration
def test_approval_sod_violation_returns_403_and_audits_failure(client, audit_repo, auth_headers):
    """
    FR-DPP-6001; NFR-SEC-012; NFR-AUD-002
    TP-DPP-ACP-002

    OpenAPI: POST /drafts/{draft_id}/approvals (operationId: createApprovalDecision)
      - 403 example: APPROVAL_DENIED_SOD_VIOLATION
    """
    draft_id = "dft_sod_001"

    # Simulate that the submitter and approver are the same (actor from auth_headers).
    payload = make_approval_decision_request(decision="APPROVE", report_version="v1.0", reauth_performed=True)
    resp = client.post(
        f"/drafts/{draft_id}/approvals",
        json={**payload, "test_submitter_id": "user_publisher_1"},
        headers=auth_headers,
    )

    assert resp.status_code == 403
    body = resp.json()
    assert_standard_error_shape(body)
    assert body["error_code"] == "APPROVAL_DENIED_SOD_VIOLATION"

    correlation_id = body["correlation_id"]
    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="APPROVAL_DECISION",
        expected_outcome="FAILURE",
        expected_reason="APPROVAL_DENIED_SOD_VIOLATION",
    )


@pytest.mark.integration
def test_approval_requires_reauth_returns_403_and_audits_failure(
    client, audit_repo, approval_auth_headers
):
    """
    FR-DPP-6002; NFR-SEC-002; NFR-AUD-002
    TP-DPP-ACP-003

    OpenAPI: POST /drafts/{draft_id}/approvals (operationId: createApprovalDecision)
      - 403 example: APPROVAL_DENIED
    """
    draft_id = "dft_reauth_001"
    payload = make_approval_decision_request(decision="APPROVE", report_version="v1.0", reauth_performed=False)
    resp = client.post(f"/drafts/{draft_id}/approvals", json=payload, headers=approval_auth_headers)

    assert resp.status_code == 403
    body = resp.json()
    assert_standard_error_shape(body)
    assert body["error_code"] == "APPROVAL_DENIED"

    correlation_id = body["correlation_id"]
    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="APPROVAL_DECISION",
        expected_outcome="FAILURE",
        expected_reason="APPROVAL_DENIED",
    )


@pytest.mark.integration
def test_publish_requires_approval_returns_403_and_audits_failure(
    client, audit_repo, auth_headers, idempotency_key
):
    """
    FR-DPP-3001..3002; FR-DPP-6003; NFR-ERR-002; NFR-AUD-002
    TP-DPP-ACP-004

    OpenAPI: POST /drafts/{draft_id}/publish (operationId: publishDraft)
      - 403 example: PUBLISH_DENIED_APPROVAL_REQUIRED
    """
    draft_id = "dft_needs_approval_001"
    payload = make_publish_request(target_version="v1.0")

    resp = client.post(
        f"/drafts/{draft_id}/publish",
        json=payload,
        headers={**auth_headers, "Idempotency-Key": idempotency_key},
    )

    assert resp.status_code == 403
    body = resp.json()
    assert_standard_error_shape(body)
    assert body["error_code"] == "PUBLISH_DENIED_APPROVAL_REQUIRED"

    correlation_id = body["correlation_id"]
    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="PUBLISH",
        expected_outcome="FAILURE",
        expected_reason="PUBLISH_DENIED_APPROVAL_REQUIRED",
    )


@pytest.mark.integration
def test_publish_happy_path_returns_200_and_audits_success(
    client, audit_repo, auth_headers, idempotency_key
):
    """
    FR-DPP-8003..8005; FR-DPP-4002..4004; FR-DPP-9001..9005; NFR-AUD-002
    (Publish happy path)

    OpenAPI: POST /drafts/{draft_id}/publish (operationId: publishDraft) -> 200 PublishResponse
    """
    draft_id = "dft_ready_to_publish_001"
    payload = make_publish_request(target_version="v1.0")

    resp = client.post(
        f"/drafts/{draft_id}/publish",
        json={**payload, "test_force_policy_decision": "PERMIT"},
        headers={**auth_headers, "Idempotency-Key": idempotency_key},
    )

    assert resp.status_code == 200
    body = resp.json()

    # PublishResponse requires: product_id, version, permalink, evidence_manifest_ref
    assert isinstance(body.get("product_id"), str) and body["product_id"]
    assert isinstance(body.get("version"), str) and body["version"]
    assert isinstance(body.get("permalink"), str) and body["permalink"]
    assert isinstance(body.get("evidence_manifest_ref"), str) and body["evidence_manifest_ref"]

    # Correlation ID required for audit reconstruction (design intent)
    correlation_id = body.get("correlation_id")
    assert correlation_id, "Expected correlation_id in publish response for traceability"

    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="PUBLISH",
        expected_outcome="SUCCESS",
    )
