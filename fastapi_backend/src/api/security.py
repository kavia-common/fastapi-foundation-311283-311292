from __future__ import annotations

from typing import Optional


# PUBLIC_INTERFACE
def actor_id_from_authorization_header(authorization: Optional[str]) -> str:
    """
    Extract a stable actor_id from the Authorization header.

    Tests pass Authorization: "Bearer test-token-for-<actor_id>".

    This is a deterministic placeholder (real JWT verification is out of scope for this TDD suite).
    """
    if not authorization:
        return "anonymous"

    parts = authorization.strip().split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
        prefix = "test-token-for-"
        if token.startswith(prefix) and len(token) > len(prefix):
            return token[len(prefix) :]
        return token

    return authorization
