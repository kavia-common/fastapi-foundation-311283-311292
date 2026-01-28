# FastAPI Backend Tests — Data Product Publishing (TDD)

This `tests/` suite is written **TDD-first** for the **Data Product Publishing workflow** as specified in:

- OpenAPI contract:
  - `kavia-docs/CodeWiki/Specs/ArchitectureSpecs/data-product-publishing-openapi.yaml`
- Class design targets:
  - `kavia-docs/CodeWiki/Specs/DetailedDesigns/python-class-definitions.md`
- Test Plan + RTM:
  - `kavia-docs/CodeWiki/Specs/Other/data-product-publishing-test-plan.md`
  - `kavia-docs/CodeWiki/Specs/Analysis/requirements-traceability-matrix.md`

## What is being validated

Primary focus areas (per user request):

1. **Registration submission** (`POST /drafts`, `operationId: submitDraft`)
2. **Validation / quality gate failures** (`POST /drafts/{draft_id}/validations`, `operationId: runValidation`)
   - Mandatory gate failures must return **422** with stable gate error codes.
3. **Approval** (`POST /drafts/{draft_id}/approvals`, `operationId: createApprovalDecision`)
4. **Publish** (`POST /drafts/{draft_id}/publish`, `operationId: publishDraft`)

For each endpoint, tests include negative cases asserting:

- Correct HTTP status and standardized error response shape (`error_code`, `message`, `correlation_id`, `timestamp_utc`, `retryable`)
- An **AuditLog entry is created** capturing:
  - `event_type`
  - `actor_id` (user_id or service principal)
  - `timestamp_utc`
  - `correlation_id` / request_id
  - `outcome` (`SUCCESS`/`FAILURE`)
  - `reason` / `error_code`
  - `payload_hash` (or a safe payload reference)

## Important note (TDD / placeholder app)

The repository currently contains only a minimal FastAPI scaffold (health check). These tests therefore **expect workflow endpoints and dependency injection hooks to exist**, and will fail until the application code is implemented to match the OpenAPI + design.

`tests/conftest.py` intentionally tries to import:

- `src.api.main:app` (existing), and expects future code to expose:
  - `app.state.audit_log_repo` (or equivalent)
  - override hooks to inject an in-memory audit repository in tests

## How to run

From the backend container root:

```bash
cd fastapi-foundation-311283-311292/fastapi_backend
pytest -q
```

## Files

- `test_registration.py`: draft submission tests (+ audit assertions)
- `test_quality_gates.py`: validation/gate failure parametrized tests (+ audit assertions)
- `test_approval_publish.py`: approval + publish tests (+ audit assertions)
- `test_audit_logging.py`: shared audit log behavior tests and invariants
- `test_support/`: helper mocks, factories, and audit repo

## Traceability

Tests include comments referencing:
- Requirement IDs (e.g., `FR-DPP-1003`, `NFR-ERR-001`)
- OpenAPI paths and `operationId`s
- Test Plan IDs (e.g., `TP-DPP-REG-001`)
"""
