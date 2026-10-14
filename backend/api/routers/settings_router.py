"""
AgentOS — Settings Router

GET  /api/v1/settings — Get user settings
PUT  /api/v1/settings — Update user settings
"""

import logging

from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from typing import Optional

from backend.api.dependencies.auth import get_current_user, AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_factory(request: Request):
    factory = getattr(request.app.state, "factory", None)
    if not factory:
        raise HTTPException(status_code=500, detail="Server not initialized")
    return factory


class SettingsUpdate(BaseModel):
    theme: Optional[str] = None                    # "dark" | "light"
    autonomy_level: Optional[int] = None           # 0-3
    default_model: Optional[str] = None            # validated Gemini model ID
    notifications_enabled: Optional[bool] = None
    daily_token_limit: Optional[int] = None
    auto_approve_low_risk: Optional[bool] = None


@router.get("")
async def get_settings(
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Get the current user's settings."""
    factory = _get_factory(request)
    settings = await factory.settings_repo.get_settings(user.user_id)
    from backend.services.gemini_client import allowed_models
    return {"settings": settings, "available_models": allowed_models()}


@router.put("")
async def update_settings(
    body: SettingsUpdate,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
):
    """Update user settings (merge semantics)."""
    factory = _get_factory(request)

    # Build updates dict from non-None fields
    updates = {}
    for field, value in body.model_dump().items():
        if value is not None:
            # Validate specific fields
            if field == "autonomy_level" and not (0 <= value <= 3):
                raise HTTPException(status_code=400, detail="Autonomy level must be 0-3")
            if field == "theme" and value not in ("dark", "light"):
                raise HTTPException(status_code=400, detail="Theme must be 'dark' or 'light'")
            if field == "default_model":
                from backend.services.gemini_client import allowed_models
                if value not in allowed_models():
                    raise HTTPException(status_code=400, detail="Model is not enabled on this server")
            updates[field] = value

    if not updates:
        raise HTTPException(status_code=400, detail="No settings to update")

    await factory.settings_repo.update_settings(user.user_id, updates)
    settings = await factory.settings_repo.get_settings(user.user_id)

    await factory.audit_repo.log_event({
        "event_type": "SETTINGS_UPDATED",
        "actor_id": user.user_id,
        "actor_type": "USER",
        "resource_id": user.user_id,
        "details": {"updated_fields": list(updates.keys())},
    })

    from backend.services.gemini_client import allowed_models
    return {"settings": settings, "available_models": allowed_models()}
