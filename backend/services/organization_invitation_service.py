"""One shared invitation service for every membership-creation path
(Phase 1.5). Both the invitations route and the legacy members alias call
this — there is exactly one place that can create an invitation, and no
ordinary route that creates membership without acceptance."""
from __future__ import annotations

import hashlib
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

INVITATION_TTL_DAYS = 7


class InvitationError(Exception):
    """Raised with a user-safe message; routers map it to HTTP 409/422."""

    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


async def create_invitation(
    factory,
    *,
    org_id: str,
    org: Dict[str, Any],
    inviter_id: str,
    inviter_role: str,
    email: str,
    role: str,
    ttl_days: int = INVITATION_TTL_DAYS,
) -> Dict[str, Any]:
    """Validate and create a pending invitation. Returns the payload with the
    one-time token. Raises InvitationError on policy violations.

    Steps (Phase 1.5): validate role → normalize email → check existing
    membership → check owner-role policy → check duplicate pending →
    generate high-entropy token → store only its hash → audit event."""
    if role not in ("admin", "member", "viewer"):
        raise InvitationError(f"role must be one of ['admin', 'member', 'viewer']", 422)
    if role == "admin" and inviter_role != "owner":
        raise InvitationError("Only the owner can appoint an admin", 403)

    from backend.security.input_sanitizer import InputValidationError, sanitize_email
    try:
        email = sanitize_email(email)
    except InputValidationError as e:
        raise InvitationError(e.message, 400)

    # Existing members are never invited; the owner's role is fixed.
    target = await factory.user_repo.get_by_email(email)
    if target:
        if await factory.org_repo.get_member_role(org_id, target["id"]) is not None:
            raise InvitationError("Already a member; use the owner-only role endpoint", 409)
        if target["id"] == org["owner_id"] and role != "owner":
            raise InvitationError("The owner's role is fixed", 409)

    token = _secrets.token_urlsafe(32)  # high-entropy; raw token returned ONCE
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=ttl_days)).isoformat()

    invite = await factory.org_repo.create_invitation(
        org_id, email, role, inviter_id, token_hash, expires_at)
    if not invite:
        raise InvitationError("A pending invitation for this email already exists", 409)

    await factory.audit_repo.log_event({
        "event_type": "ORG_INVITATION_CREATED",
        "actor_id": inviter_id, "actor_type": "USER",
        "resource_id": org_id,
        # No raw token, no email beyond the invited address itself.
        "details": {"email": email, "role": role},
    })
    return {"invitation_id": invite["invitation_id"], "org_id": org_id, "email": email,
            "role": role, "expires_at": invite["expires_at"], "token": token}


async def accept_invitation(factory, *, token: str, user_id: str, user_email: str) -> Dict[str, Any]:
    """Acceptance: verify the token's hash, enforce recipient-identity
    verification (Phase 1.3 — an unverified email address is insufficient
    proof of control), then delegate to the repo's atomic accept."""
    import hashlib
    from backend.config.settings import settings as app_settings

    if getattr(app_settings, "REQUIRE_VERIFIED_EMAIL_FOR_INVITES", True):
        account = await factory.user_repo.get_by_id(user_id)
        if account is None:
            raise InvitationError("Account not found", 404)
        if not account.get("email_verified"):
            raise InvitationError(
                "Verify your email address before accepting organization invitations.", 403)

    token_hash = hashlib.sha256(token.encode()).hexdigest()
    try:
        membership = await factory.org_repo.accept_invitation(token_hash, user_id, user_email)
    except ValueError as e:
        raise InvitationError(str(e), 409)
    await factory.audit_repo.log_event({
        "event_type": "ORG_INVITATION_ACCEPTED",
        "actor_id": user_id, "actor_type": "USER",
        "resource_id": membership["org_id"],
        "details": {"role": membership["role"]},
    })
    return membership
