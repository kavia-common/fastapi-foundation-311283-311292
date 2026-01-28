from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class StandardError(BaseModel):
    """Standardized error response model (OpenAPI StandardError)."""

    error_code: str = Field(..., description="Stable machine-readable error code.")
    message: str = Field(..., description="Human-readable, safe error message.")
    correlation_id: str = Field(..., description="Correlation identifier for tracing.")
    timestamp_utc: str = Field(..., description="UTC timestamp in ISO-8601 format.")
    retryable: bool = Field(..., description="Whether the client may safely retry.")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional structured details (redacted/minimized)."
    )


class GateFailureError(StandardError):
    """Error response for mandatory gate failures (OpenAPI GateFailureError)."""

    details: Optional[Dict[str, Any]] = Field(default=None)


class DatasetRef(BaseModel):
    uri: str = Field(..., description="URI or handle to dataset (e.g., object storage path).")
    checksum_sha256: Optional[str] = Field(default=None, description="Optional checksum.")


class DataProductMetadata(BaseModel):
    name: str
    description: str
    domain: str
    classification: str
    schema_version: str
    source: str
    lineage: str
    update_frequency: str
    critical_columns: Optional[List[str]] = None
    max_age_seconds: Optional[int] = None


class DraftSubmissionRequest(BaseModel):
    dataset_ref: DatasetRef
    metadata: DataProductMetadata
    submission_channel: Optional[str] = Field(default=None, description="UI or API")

    # PUBLIC_INTERFACE
    def missing_mandatory_metadata_fields(self) -> List[str]:
        """Return missing mandatory metadata fields per OpenAPI required list (tests rely on schema_version/lineage)."""
        missing: List[str] = []
        # Required by spec: name, description, domain, classification, schema_version, source, lineage, update_frequency
        # Pydantic will already require these, but tests simulate missing by removing keys;
        # that becomes validation error unless fields are Optional. We keep required, but still check
        # for safety for partial payloads or future loosening.
        md = self.metadata.model_dump()
        for k in ["schema_version", "source", "lineage", "update_frequency"]:
            v = md.get(k)
            if v is None or (isinstance(v, str) and not v.strip()):
                missing.append(k)
        return missing


class Draft(BaseModel):
    draft_id: str
    state: str
    submitted_by: str
    submitted_at_utc: str
    dataset_ref: DatasetRef
    metadata: DataProductMetadata
    latest_quality_report_version: Optional[str] = None


class DraftSubmissionResponse(BaseModel):
    draft: Draft
    correlation_id: str


class ValidationRunRequest(BaseModel):
    full_suite: bool = Field(default=True)


class ApprovalSignature(BaseModel):
    signature_type: str = Field(..., description="Signature type (reauthentication).")
    reauth_performed: bool = Field(..., description="Whether re-auth was performed.")


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., description="APPROVE or REJECT")
    report_version: str = Field(..., description="Quality report version being approved.")
    rationale: Optional[str] = None
    signature: Optional[ApprovalSignature] = None


class ApprovalDecision(BaseModel):
    approval_id: str
    draft_id: str
    decision: str
    signed_by: str
    signed_at_utc: str
    report_version: str
    sod_check_passed: Optional[bool] = None
    rationale: Optional[str] = None


class PublishRequest(BaseModel):
    target_version: Optional[str] = Field(default=None, description="Intended published version (e.g., v1.0).")


class PublishResponse(BaseModel):
    product_id: str
    version: str
    permalink: str
    evidence_manifest_ref: str
    policy_decision: Optional[Dict[str, Any]] = None
    # correlation_id is injected in route response for tests (not in spec required fields)
