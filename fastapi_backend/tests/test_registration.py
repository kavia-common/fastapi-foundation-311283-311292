from __future__ import annotations

import pytest

from tests.test_support.assertions import assert_audit_logged, assert_standard_error_shape
from tests.test_support.factories import (
    make_missing_metadata_submission_request,
    make_valid_draft_submission_request,
)


@pytest.mark.integration
def test_submit_draft_happy_path_creates_audit_log(client, audit_repo, auth_headers):
    """
    FR-DPP-1002, FR-DPP-1003, FR-DPP-1004; NFR-AUD-002
    TP-DPP-REG-001

    OpenAPI: POST /drafts (operationId: submitDraft)
    """
    payload = make_valid_draft_submission_request()
    resp = client.post("/drafts", json=payload, headers=auth_headers)

    # TDD: expected success per OpenAPI
    assert resp.status_code == 201
    body = resp.json()

    # DraftSubmissionResponse requires: { draft, correlation_id }
    assert "draft" in body
    assert "correlation_id" in body and isinstance(body["correlation_id"], str) and body["correlation_id"]

    correlation_id = body["correlation_id"]

    # Audit: success event must exist.
    # Expected event_type to be implemented later by app code (suggested).
    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="DRAFT_SUBMITTED",
        expected_outcome="SUCCESS",
    )


@pytest.mark.integration
def test_submit_draft_missing_mandatory_metadata_returns_422_and_audits_failure(
    client, audit_repo, auth_headers
):
    """
    FR-DPP-1003; NFR-DATA-021; NFR-ERR-001, NFR-ERR-002; NFR-AUD-002
    TP-DPP-REG-002

    OpenAPI: POST /drafts (operationId: submitDraft)
      - 422: MetadataValidationFailedError (StandardError with error_code METADATA_VALIDATION_FAILED)
    """
    payload = make_missing_metadata_submission_request()
    resp = client.post("/drafts", json=payload, headers=auth_headers)

    assert resp.status_code == 422
    body = resp.json()
    assert_standard_error_shape(body)
    assert body["error_code"] == "METADATA_VALIDATION_FAILED"

    correlation_id = body["correlation_id"]

    # Audit: failure event recorded with reason/error_code.
    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="DRAFT_SUBMITTED",
        expected_outcome="FAILURE",
        expected_reason="METADATA_VALIDATION_FAILED",
    )


@pytest.mark.integration
def test_submit_draft_unsupported_media_type_returns_415_and_audits_failure(
    client, audit_repo, auth_headers
):
    """
    NFR-DATA-001; NFR-ERR-002; NFR-AUD-002
    TP-DPP-REG-003

    OpenAPI: POST /drafts (operationId: submitDraft)
      - 415: UnsupportedMediaTypeError (StandardError with error_code UNSUPPORTED_MEDIA_TYPE)
    """
    payload = "not json"
    resp = client.post("/drafts", data=payload, headers={**auth_headers, "Content-Type": "text/plain"})

    assert resp.status_code == 415
    body = resp.json()
    assert_standard_error_shape(body)
    assert body["error_code"] == "UNSUPPORTED_MEDIA_TYPE"

    correlation_id = body["correlation_id"]

    assert_audit_logged(
        audit_repo,
        correlation_id=correlation_id,
        expected_event_type="DRAFT_SUBMITTED",
        expected_outcome="FAILURE",
        expected_reason="UNSUPPORTED_MEDIA_TYPE",
    )
