from __future__ import annotations

from typing import Any, Dict


# PUBLIC_INTERFACE
def make_valid_draft_submission_request(
    *,
    dataset_uri: str = "s3://mock-bucket/datasets/dp1/v1.parquet",
    checksum_sha256: str = "a" * 64,
    classification: str = "Internal",
    schema_version: str = "1.2.0",
    max_age_seconds: int = 86400,
    submission_channel: str = "API",
) -> Dict[str, Any]:
    """
    Create a valid DraftSubmissionRequest payload per OpenAPI.

    OpenAPI: `POST /drafts` (operationId: submitDraft)
    Schema: DraftSubmissionRequest -> { dataset_ref, metadata, submission_channel? }
    """
    return {
        "dataset_ref": {"uri": dataset_uri, "checksum_sha256": checksum_sha256},
        "metadata": {
            "name": "dp1",
            "description": "Test data product",
            "domain": "clinical",
            "classification": classification,
            "schema_version": schema_version,
            "source": "test_source_system",
            "lineage": "upstream_system->transform->dp1",
            "update_frequency": "daily",
            "critical_columns": ["patient_id"],
            "max_age_seconds": max_age_seconds,
        },
        "submission_channel": submission_channel,
    }


# PUBLIC_INTERFACE
def make_missing_metadata_submission_request() -> Dict[str, Any]:
    """
    Create an invalid submission missing mandatory metadata fields.

    Expected error: 422 METADATA_VALIDATION_FAILED (per OpenAPI components/responses)
    """
    req = make_valid_draft_submission_request()
    # remove required fields
    req["metadata"].pop("schema_version", None)
    req["metadata"].pop("lineage", None)
    return req


# PUBLIC_INTERFACE
def make_validation_run_request(*, full_suite: bool = True) -> Dict[str, Any]:
    """
    Create a ValidationRunRequest payload.

    OpenAPI: `POST /drafts/{draft_id}/validations` (operationId: runValidation)
    """
    return {"full_suite": full_suite}


# PUBLIC_INTERFACE
def make_approval_decision_request(
    *,
    decision: str = "APPROVE",
    report_version: str = "v1.0",
    rationale: str = "Looks good.",
    reauth_performed: bool = True,
) -> Dict[str, Any]:
    """
    Create ApprovalDecisionRequest payload per OpenAPI.

    OpenAPI: `POST /drafts/{draft_id}/approvals` (operationId: createApprovalDecision)
    """
    return {
        "decision": decision,
        "report_version": report_version,
        "rationale": rationale,
        "signature": {"signature_type": "reauthentication", "reauth_performed": reauth_performed},
    }


# PUBLIC_INTERFACE
def make_publish_request(*, target_version: str = "v1.0") -> Dict[str, Any]:
    """
    Create PublishRequest payload per OpenAPI.

    OpenAPI: `POST /drafts/{draft_id}/publish` (operationId: publishDraft)
    """
    return {"target_version": target_version}
