from __future__ import annotations

"""
FastAPI backend for the Data Product Publishing workflow.

This application implements a subset of the OpenAPI contract located at:
`kavia-docs/CodeWiki/Specs/ArchitectureSpecs/data-product-publishing-openapi.yaml`

Focus (per tests):
- POST /drafts (submitDraft)
- POST /drafts/{draft_id}/validations (runValidation)
- POST /drafts/{draft_id}/approvals (createApprovalDecision)
- POST /drafts/{draft_id}/publish (publishDraft)

Key behaviors:
- Standardized error response body: {error_code, message, correlation_id, timestamp_utc, retryable, details?}
- Explicit gate-failure 422 responses with stable error_code (e.g., VAL_FRESHNESS_CHECK_FAILED)
- Audit logs must be created for both success and failure outcomes.
- Tests inject an in-memory audit repo via `app.state.audit_log_repo`.

Important note for this task:
- POST /drafts must enforce Unsupported Media Type (415) *before* any JSON/Pydantic parsing.
- Error/exception handlers must never include raw bytes in JSON responses (avoid TypeError).
"""

import uuid
from typing import Any, Dict, Optional

from fastapi import Body, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.models import (
    ApprovalDecision,
    ApprovalDecisionBody,
    DraftSubmissionRequest,
    DraftSubmissionResponse,
    GateFailureError,
    PublishBody,
    PublishResponse,
    StandardError,
    ValidationRunBody,
)
from src.api.repos import InMemoryDraftRepository
from src.api.security import actor_id_from_authorization_header
from src.api.service import DataProductPublishingService
from src.api.types import AuditRepoProtocol
from src.api.utils import utc_now_iso_z

openapi_tags = [
    {"name": "Drafts", "description": "Draft submission and remediation actions."},
    {"name": "Validations", "description": "Validation runs and quality gate reports."},
    {"name": "Approvals", "description": "Approval actions including electronic signature semantics."},
    {"name": "Publishing", "description": "Publish operations and policy decision hooks."},
]


def _get_audit_repo_from_app_state(app: FastAPI) -> AuditRepoProtocol:
    """
    Internal helper to retrieve audit repository from app.state.

    Tests set `app.state.audit_log_repo` to an in-memory repo.
    If it does not exist, a minimal no-op fallback is provided by src.api.repos.
    """
    repo = getattr(app.state, "audit_log_repo", None)
    if repo is None:
        # Fallback should not be used by tests, but avoids runtime crashes.
        from src.api.repos import NoOpAuditLogRepository

        repo = NoOpAuditLogRepository()
        app.state.audit_log_repo = repo
    return repo  # type: ignore[return-value]


def _correlation_id_from_request(request: Request) -> str:
    """Prefer an inbound correlation id header if present; otherwise generate."""
    inbound = request.headers.get("X-Correlation-Id")
    return inbound if inbound else str(uuid.uuid4())


def _standard_error(
    *,
    error_code: str,
    message: str,
    correlation_id: str,
    http_status: int,
    retryable: bool,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    """Create JSONResponse for StandardError shape."""
    payload = StandardError(
        error_code=error_code,
        message=message,
        correlation_id=correlation_id,
        timestamp_utc=utc_now_iso_z(),
        retryable=retryable,
        details=details,
    ).model_dump(exclude_none=True)
    return JSONResponse(status_code=http_status, content=payload)


def _event_type_for_request(request: Request) -> str:
    """Map request path to the event type expected by tests."""
    path = request.url.path
    if path == "/drafts" and request.method.upper() == "POST":
        return "DRAFT_SUBMITTED"
    if path.endswith("/validations") and request.method.upper() == "POST":
        return "VALIDATION_RUN"
    if path.endswith("/approvals") and request.method.upper() == "POST":
        return "APPROVAL_DECISION"
    if path.endswith("/publish") and request.method.upper() == "POST":
        return "PUBLISH"
    # fallback
    return "UNKNOWN_EVENT"


def _json_safe(obj: Any) -> Any:
    """
    Convert potentially non-JSON-serializable values into safe representations.

    This is used defensively in exception handlers because FastAPI's validation errors
    can embed raw bytes (e.g., input=b'not json'), which would otherwise crash JSONResponse.
    """
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return obj


app = FastAPI(
    title="Data Product Publishing API",
    description="FastAPI implementation of the Data Product Publishing workflow (TDD subset).",
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup_init_state() -> None:
    """Initialize in-memory dependencies suitable for tests and local runs."""
    # Draft repository (in-memory)
    if not hasattr(app.state, "draft_repo"):
        app.state.draft_repo = InMemoryDraftRepository()

    # Audit repo is set by tests in conftest; if not, lazily created by helper.
    if not hasattr(app.state, "audit_log_repo"):
        from src.api.repos import NoOpAuditLogRepository

        app.state.audit_log_repo = NoOpAuditLogRepository()


# --- Exception handlers (ensure standardized errors + audit) ---


@app.exception_handler(RequestValidationError)
async def _handle_request_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Convert FastAPI/Pydantic validation errors into standardized error bodies and audit them.

    Important behavior for this TDD suite:
    - POST /drafts: Content-Type enforcement is handled in-route (415 before parsing).
      If we still receive RequestValidationError for /drafts, JSON was supplied but model
      validation failed -> standardized 400.
    - Other endpoints: malformed/mismatched request bodies should be 422 (standardized).
    - Never include raw bytes in response bodies (sanitize exc.errors()).
    """
    correlation_id = _correlation_id_from_request(request)

    event_type = _event_type_for_request(request)
    actor_id = actor_id_from_authorization_header(request.headers.get("Authorization"))
    audit_repo = _get_audit_repo_from_app_state(request.app)

    safe_errors = _json_safe(exc.errors())

    if request.url.path == "/drafts" and request.method.upper() == "POST":
        audit_repo.append(
            event_type=event_type,
            actor_id=actor_id,
            correlation_id=correlation_id,
            outcome="FAILURE",
            reason="BAD_REQUEST",
            payload={"validation_errors": safe_errors},
            details={"path": str(request.url.path), "method": request.method},
        )
        return _standard_error(
            error_code="BAD_REQUEST",
            message="Request body is not valid JSON or contains invalid fields.",
            correlation_id=correlation_id,
            http_status=400,
            retryable=False,
            details={"validation_errors": safe_errors},
        )

    audit_repo.append(
        event_type=event_type,
        actor_id=actor_id,
        correlation_id=correlation_id,
        outcome="FAILURE",
        reason="REQUEST_VALIDATION_FAILED",
        payload={"validation_errors": safe_errors},
        details={"path": str(request.url.path), "method": request.method},
    )

    return _standard_error(
        error_code="REQUEST_VALIDATION_FAILED",
        message="Request body failed validation.",
        correlation_id=correlation_id,
        http_status=422,
        retryable=False,
        details={"validation_errors": safe_errors},
    )


@app.exception_handler(StarletteHTTPException)
async def _handle_starlette_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """
    Convert Starlette HTTP exceptions into standardized errors and audit them.

    This primarily covers malformed JSON (Starlette raises 400) when we parse JSON manually.
    """
    correlation_id = _correlation_id_from_request(request)
    event_type = _event_type_for_request(request)
    actor_id = actor_id_from_authorization_header(request.headers.get("Authorization"))
    audit_repo = _get_audit_repo_from_app_state(request.app)

    msg = str(exc.detail) if exc.detail else "Request failed."
    error_code = "BAD_REQUEST" if exc.status_code == 400 else "HTTP_ERROR"

    audit_repo.append(
        event_type=event_type,
        actor_id=actor_id,
        correlation_id=correlation_id,
        outcome="FAILURE",
        reason=error_code,
        payload={"http_status": exc.status_code, "detail": msg},
        details={"path": str(request.url.path), "method": request.method},
    )

    return _standard_error(
        error_code=error_code,
        message=msg,
        correlation_id=correlation_id,
        http_status=exc.status_code,
        retryable=False,
        details={"path": str(request.url.path)},
    )


# --- Routes ---


@app.get("/", tags=["Drafts"], summary="Health check", operation_id="health_check__get")
def health_check() -> Dict[str, str]:
    """Simple health check endpoint."""
    return {"message": "Healthy"}


@app.post(
    "/drafts",
    tags=["Drafts"],
    summary="Submit a data product draft",
    operation_id="submitDraft",
    status_code=201,
    responses={
        201: {"model": DraftSubmissionResponse},
        415: {"model": StandardError},
        422: {"model": StandardError},
    },
)
async def submit_draft(
    request: Request,
    body: bytes = Body(...),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """
    Submit a new draft.

    - Reads request body as raw bytes first to allow Content-Type enforcement *before*
      any JSON/Pydantic parsing (prevents FastAPI RequestValidationError from triggering
      on non-JSON bodies).
    - Enforces `Content-Type: application/json` and returns 415 for non-JSON payloads.
      (Tests assert 415 on `text/plain`).
    - Only after passing Content-Type check do we parse JSON and validate into
      DraftSubmissionRequest.
    - Performs semantic validation for mandatory metadata; on failure returns
      422 with error_code `METADATA_VALIDATION_FAILED`.
    - Appends an audit event for both success and failure.
    """
    correlation_id = _correlation_id_from_request(request)
    actor_id = actor_id_from_authorization_header(authorization)
    audit_repo = _get_audit_repo_from_app_state(request.app)

    # Enforce content type explicitly *before* parsing.
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        # For audit hashing, tests support bytes in payload hashing.
        audit_repo.append(
            event_type="DRAFT_SUBMITTED",
            actor_id=actor_id,
            correlation_id=correlation_id,
            outcome="FAILURE",
            reason="UNSUPPORTED_MEDIA_TYPE",
            payload={"raw_body": body},
            details={"path": str(request.url.path), "content_type": content_type},
        )
        return _standard_error(
            error_code="UNSUPPORTED_MEDIA_TYPE",
            message="Unsupported Content-Type for dataset submission.",
            correlation_id=correlation_id,
            http_status=415,
            retryable=False,
            details={"content_type": content_type},
        )

    # Now safe to parse JSON. If malformed JSON, Starlette raises 400 which our HTTPException handler standardizes.
    parsed_json = await request.json()
    submission = DraftSubmissionRequest.model_validate(parsed_json)

    missing = submission.missing_mandatory_metadata_fields()
    if missing:
        audit_repo.append(
            event_type="DRAFT_SUBMITTED",
            actor_id=actor_id,
            correlation_id=correlation_id,
            outcome="FAILURE",
            reason="METADATA_VALIDATION_FAILED",
            payload=submission.model_dump(),
            details={"missing_fields": missing},
        )
        return JSONResponse(
            status_code=422,
            content=StandardError(
                error_code="METADATA_VALIDATION_FAILED",
                message="Mandatory metadata is missing or invalid (schema_version, source, lineage, update_frequency).",
                correlation_id=correlation_id,
                timestamp_utc=utc_now_iso_z(),
                retryable=False,
                details={"missing_fields": missing},
            ).model_dump(exclude_none=True),
        )

    draft_repo: InMemoryDraftRepository = request.app.state.draft_repo
    service = DataProductPublishingService(draft_repo=draft_repo, audit_repo=audit_repo)

    draft = service.submit_draft(
        actor_id=actor_id,
        correlation_id=correlation_id,
        submission=submission,
        idempotency_key=idempotency_key,
    )

    return JSONResponse(
        status_code=201,
        content=DraftSubmissionResponse(draft=draft, correlation_id=correlation_id).model_dump(exclude_none=True),
    )


@app.post(
    "/drafts/{draft_id}/validations",
    tags=["Validations"],
    summary="Trigger a validation run",
    operation_id="runValidation",
    responses={
        200: {"model": Dict[str, Any]},  # QualityReport-like payload (tests don't validate full schema)
        202: {"model": Dict[str, Any]},  # ValidationRunAccepted-like payload
        422: {"model": GateFailureError},
    },
)
def run_validation(
    draft_id: str,
    request: Request,
    body: ValidationRunBody = Body(default_factory=ValidationRunBody),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """
    Trigger validation run and return either success (200/202) or gate failure (422).

    Tests enforce:
    - on gate failure: 422 and body.error_code == VAL_<GATE>_... plus audit FAILURE.
    - on success: 200/202 and response includes correlation_id, plus audit SUCCESS.
    """
    correlation_id = _correlation_id_from_request(request)
    actor_id = actor_id_from_authorization_header(authorization)
    audit_repo = _get_audit_repo_from_app_state(request.app)
    draft_repo: InMemoryDraftRepository = request.app.state.draft_repo

    service = DataProductPublishingService(draft_repo=draft_repo, audit_repo=audit_repo)

    try:
        result = service.run_validation(
            actor_id=actor_id,
            correlation_id=correlation_id,
            draft_id=draft_id,
            req=body.payload,
            idempotency_key=idempotency_key,
            test_force_gate_failure=body.test_force_gate_failure,
        )
    except service.GateFailure as gf:
        err = GateFailureError(
            error_code=gf.error_code,
            message=gf.message,
            correlation_id=correlation_id,
            timestamp_utc=utc_now_iso_z(),
            retryable=False,
            details=gf.details,
        )
        return JSONResponse(status_code=422, content=err.model_dump(exclude_none=True))

    return JSONResponse(status_code=result["status_code"], content=result["body"])


@app.post(
    "/drafts/{draft_id}/approvals",
    tags=["Approvals"],
    summary="Approve or reject a draft for publication",
    operation_id="createApprovalDecision",
    status_code=201,
    responses={201: {"model": ApprovalDecision}, 403: {"model": StandardError}},
)
def create_approval_decision(
    draft_id: str,
    request: Request,
    body: dict = Body(...),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """
    Record an approval decision.

    Tests send a *flat* body shape:
      { decision, report_version, signature, reauth_performed?, test_submitter_id? }

    The OpenAPI wrapper form `{ payload: {...}, test_submitter_id? }` may also be accepted
    for compatibility.
    """
    correlation_id = _correlation_id_from_request(request)
    actor_id = actor_id_from_authorization_header(authorization)
    audit_repo = _get_audit_repo_from_app_state(request.app)
    draft_repo: InMemoryDraftRepository = request.app.state.draft_repo

    # Support both flat and wrapper shapes; tests use flat.
    if isinstance(body, dict) and "payload" in body and isinstance(body.get("payload"), dict):
        parsed = ApprovalDecisionBody.model_validate(body)
        approval_req = parsed.payload
        test_submitter_id = parsed.test_submitter_id
    else:
        approval_req = ApprovalDecisionBody.model_validate({"payload": body}).payload
        test_submitter_id = body.get("test_submitter_id") if isinstance(body, dict) else None

    service = DataProductPublishingService(draft_repo=draft_repo, audit_repo=audit_repo)
    try:
        decision = service.create_approval_decision(
            actor_id=actor_id,
            correlation_id=correlation_id,
            draft_id=draft_id,
            req=approval_req,
            idempotency_key=idempotency_key,
            test_submitter_id=test_submitter_id,
        )
        return JSONResponse(status_code=201, content=decision.model_dump(exclude_none=True))
    except service.Forbidden as fe:
        return _standard_error(
            error_code=fe.error_code,
            message=fe.message,
            correlation_id=correlation_id,
            http_status=403,
            retryable=False,
            details=fe.details,
        )


@app.post(
    "/drafts/{draft_id}/publish",
    tags=["Publishing"],
    summary="Publish an approved draft",
    operation_id="publishDraft",
    responses={200: {"model": PublishResponse}, 403: {"model": StandardError}},
)
def publish_draft(
    draft_id: str,
    request: Request,
    body: dict = Body(default_factory=dict),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> JSONResponse:
    """
    Publish a draft.

    Tests send a flat body:
      { target_version, test_force_policy_decision }

    The OpenAPI wrapper `{ payload: {...}, test_force_policy_decision? }` may also be accepted.
    """
    correlation_id = _correlation_id_from_request(request)
    actor_id = actor_id_from_authorization_header(authorization)
    audit_repo = _get_audit_repo_from_app_state(request.app)
    draft_repo: InMemoryDraftRepository = request.app.state.draft_repo

    if isinstance(body, dict) and "payload" in body and isinstance(body.get("payload"), dict):
        parsed = PublishBody.model_validate(body)
        publish_req = parsed.payload
        forced_decision = parsed.test_force_policy_decision
    else:
        publish_req = PublishBody.model_validate({"payload": body}).payload
        forced_decision = body.get("test_force_policy_decision") if isinstance(body, dict) else None

    service = DataProductPublishingService(draft_repo=draft_repo, audit_repo=audit_repo)
    try:
        pub = service.publish_draft(
            actor_id=actor_id,
            correlation_id=correlation_id,
            draft_id=draft_id,
            req=publish_req,
            idempotency_key=idempotency_key,
            test_force_policy_decision=forced_decision,
        )
        resp_body = pub.model_dump(exclude_none=True)
        resp_body["correlation_id"] = correlation_id
        return JSONResponse(status_code=200, content=resp_body)
    except service.Forbidden as fe:
        return _standard_error(
            error_code=fe.error_code,
            message=fe.message,
            correlation_id=correlation_id,
            http_status=403,
            retryable=False,
            details=fe.details,
        )
