from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from src.api.models import Draft, DraftSubmissionRequest
from src.api.types import AuditRepoProtocol
from src.api.utils import utc_now_iso_z


@dataclass
class DraftRecord:
    draft: Draft
    # Track simplified workflow artifacts for tests
    last_validation_passed: bool = False
    approved: bool = False
    submitter_id: Optional[str] = None


class InMemoryDraftRepository:
    """A minimal in-memory draft repository suitable for tests."""

    def __init__(self) -> None:
        self._drafts: Dict[str, DraftRecord] = {}

    # PUBLIC_INTERFACE
    def create_draft(self, *, draft_id: str, submitted_by: str, submission: DraftSubmissionRequest) -> DraftRecord:
        """Create and store a draft record."""
        draft = Draft(
            draft_id=draft_id,
            state="DRAFT_READY",
            submitted_by=submitted_by,
            submitted_at_utc=utc_now_iso_z(),
            dataset_ref=submission.dataset_ref,
            metadata=submission.metadata,
            latest_quality_report_version=None,
        )
        rec = DraftRecord(draft=draft, submitter_id=submitted_by)
        self._drafts[draft_id] = rec
        return rec

    # PUBLIC_INTERFACE
    def get(self, draft_id: str) -> Optional[DraftRecord]:
        """Get a draft record if present."""
        return self._drafts.get(draft_id)

    # PUBLIC_INTERFACE
    def ensure_exists_for_tests(self, draft_id: str, *, submitter_id: Optional[str] = None) -> DraftRecord:
        """
        Ensure a draft exists even if it wasn't explicitly created via POST /drafts.

        Some tests reference arbitrary draft ids directly for approval/publish negative paths.
        """
        rec = self._drafts.get(draft_id)
        if rec:
            if submitter_id is not None:
                rec.submitter_id = submitter_id
                rec.draft.submitted_by = submitter_id
            return rec

        # Create a minimal draft with placeholder metadata.
        placeholder_submission = DraftSubmissionRequest(
            dataset_ref={"uri": "s3://placeholder/dataset", "checksum_sha256": "a" * 64},
            metadata={
                "name": "placeholder",
                "description": "placeholder",
                "domain": "placeholder",
                "classification": "Internal",
                "schema_version": "1.0.0",
                "source": "placeholder",
                "lineage": "placeholder",
                "update_frequency": "daily",
            },
            submission_channel="API",
        )
        new_submitter = submitter_id or "user_publisher_1"
        return self.create_draft(draft_id=draft_id, submitted_by=new_submitter, submission=placeholder_submission)

    # PUBLIC_INTERFACE
    def next_draft_id(self) -> str:
        """Generate a new draft id."""
        return f"dft_{uuid.uuid4().hex[:10]}"

    # PUBLIC_INTERFACE
    def mark_validation(self, draft_id: str, *, passed: bool, report_version: str) -> None:
        """Update draft state based on validation outcome."""
        rec = self.ensure_exists_for_tests(draft_id)
        rec.last_validation_passed = passed
        rec.draft.latest_quality_report_version = report_version
        rec.draft.state = "VALIDATED" if passed else "FAILED_VALIDATION"

    # PUBLIC_INTERFACE
    def mark_approved(self, draft_id: str, *, approved: bool) -> None:
        """Update draft state based on approval outcome."""
        rec = self.ensure_exists_for_tests(draft_id)
        rec.approved = approved
        rec.draft.state = "APPROVED" if approved else rec.draft.state


class NoOpAuditLogRepository(AuditRepoProtocol):
    """Fallback audit repo used when none injected. Does nothing."""

    # PUBLIC_INTERFACE
    def append(  # type: ignore[override]
        self,
        *,
        event_type: str,
        actor_id: str,
        correlation_id: str,
        outcome: str,
        reason: Optional[str] = None,
        payload: Optional[dict] = None,
        payload_ref: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        """No-op append; returns a minimal dict-like object."""
        return {
            "event_type": event_type,
            "actor_id": actor_id,
            "correlation_id": correlation_id,
            "outcome": outcome,
            "reason": reason,
            "payload_ref": payload_ref,
            "details": details or {},
        }
