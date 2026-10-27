"""Per-request LLM key overrides for Gemini, Grok, Groq, and Hugging Face."""

from contextvars import ContextVar
from typing import Any, Dict, Optional

from backend.config.settings import settings

_user_gemini_key: ContextVar[Optional[str]] = ContextVar("user_gemini_key", default=None)
_user_grok_key: ContextVar[Optional[str]] = ContextVar("user_grok_key", default=None)
_user_groq_key: ContextVar[Optional[str]] = ContextVar("user_groq_key", default=None)
_user_hf_token: ContextVar[Optional[str]] = ContextVar("user_hf_token", default=None)


_user_model: ContextVar[Optional[str]] = ContextVar("user_model", default=None)

_user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)


def get_user_id() -> Optional[str]:
    return _user_id.get()


def get_user_model() -> Optional[str]:
    return _user_model.get()


async def load_user_model(settings_repo, user_id: str, preferred: Optional[str] = None):
    _user_model.set(None)
    saved = await settings_repo.get_settings(user_id) if settings_repo and user_id else {}
    selected = preferred or (saved or {}).get("default_model")
    if active_llm_provider() == "huggingface":
        if selected and selected != settings.HF_MODEL:
            selected = settings.HF_MODEL
        _user_model.set(selected or settings.HF_MODEL)
        return _user_model.get()
    if selected:
        from backend.services.gemini_client import allowed_models
        if selected not in allowed_models():
            raise ValueError("Selected model is not enabled on this server")
        _user_model.set(selected)
    return selected


def set_user_gemini_key(key: Optional[str]) -> None:
    _user_gemini_key.set((key or "").strip() or None)


def get_user_gemini_key() -> Optional[str]:
    return _user_gemini_key.get()


def set_user_grok_key(key: Optional[str]) -> None:
    _user_grok_key.set((key or "").strip() or None)


def get_user_grok_key() -> Optional[str]:
    return _user_grok_key.get()


def effective_gemini_key() -> Optional[str]:
    return get_user_gemini_key() or settings.GEMINI_API_KEY


def effective_grok_key() -> Optional[str]:
    return get_user_grok_key() or settings.XAI_API_KEY


def set_user_groq_key(key: Optional[str]) -> None:
    _user_groq_key.set((key or "").strip() or None)


def get_user_groq_key() -> Optional[str]:
    return _user_groq_key.get()


def effective_groq_key() -> Optional[str]:
    return get_user_groq_key() or settings.GROQ_API_KEY


def set_user_hf_token(token: Optional[str]) -> None:
    _user_hf_token.set((token or "").strip() or None)


def effective_hf_token() -> Optional[str]:
    import os
    return get_user_hf_token() or settings.HF_TOKEN or (os.environ.get("HF_TOKEN") or "").strip() or None


def get_user_hf_token() -> Optional[str]:
    return _user_hf_token.get()


def active_llm_provider() -> str:
    """Resolve the provider from explicit config or available credentials."""
    import os
    selected = (settings.LLM_PROVIDER or "auto").strip().lower()
    if selected != "auto":
        return selected
    if effective_gemini_key() or (os.environ.get("GEMINI_API_KEY") or "").strip():
        return "gemini"
    if settings.GOOGLE_CLOUD_PROJECT or (os.environ.get("GOOGLE_CLOUD_PROJECT") or "").strip():
        return "vertex"
    if effective_groq_key() or (os.environ.get("GROQ_API_KEY") or "").strip():
        return "groq"
    if effective_hf_token():
        return "huggingface"
    return "gemini"


def gemini_adk_kwargs() -> Dict[str, Any]:
    """Client kwargs for ADK Gemini so BYOK vault keys reach planner/orchestrator.

    Vertex location is always settings.GOOGLE_CLOUD_REGION (GOOGLE_CLOUD_REGION env).
    Do not hardcode us-central1 or any other region here.
    """
    provider = active_llm_provider()
    key = effective_gemini_key()
    if provider == "gemini" and key:
        return {"api_key": key}
    if provider in {"groq", "huggingface"}:
        raise ValueError(f"{provider} is active and cannot be configured as a Gemini ADK client")
    if provider == "gemini" and settings.LLM_PROVIDER != "auto":
        raise ValueError("LLM_PROVIDER=gemini requires GEMINI_API_KEY")
    if provider == "vertex" and not (settings.GOOGLE_CLOUD_PROJECT or __import__("os").environ.get("GOOGLE_CLOUD_PROJECT")):
        raise ValueError("LLM_PROVIDER=vertex requires GOOGLE_CLOUD_PROJECT")
    return {
        "vertexai": True,
        "project": settings.GOOGLE_CLOUD_PROJECT,
        "location": settings.GOOGLE_CLOUD_REGION,
    }


def adk_gemini(model: Optional[str] = None, *, tools: Optional[list] = None):
    """Return the configured ADK provider (Gemini, Vertex, Groq, or Hugging Face)."""
    provider = active_llm_provider()
    if provider == "groq":
        if not effective_groq_key():
            raise ValueError("LLM_PROVIDER=groq requires GROQ_API_KEY")
        from backend.services.groq_adk import GroqADK
        return GroqADK(model=settings.GROQ_MODEL)
    if provider == "huggingface":
        if not effective_hf_token():
            raise ValueError("LLM_PROVIDER=huggingface requires HF_TOKEN")
        from backend.services.huggingface_adk import HuggingFaceADK
        return HuggingFaceADK(model=settings.HF_MODEL)
    from google.adk.models.google_llm import Gemini
    from backend.services.gemini_client import candidate_models

    kwargs: Dict[str, Any] = {
        "model": candidate_models(model)[0],
        "client_kwargs": gemini_adk_kwargs(),
    }
    if tools is not None:
        kwargs["tools"] = tools
    return Gemini(**kwargs)


async def _load_named_key(secrets_repo, user_id: str, name: str, fields: tuple) -> Optional[str]:
    try:
        from backend.api.routers.credentials import load_credential
        cred = await load_credential(secrets_repo, user_id, name)
        for field in fields:
            val = cred.get(field)
            if isinstance(val, str) and val.strip():
                return val.strip()
    except Exception:
        return None
    return None


async def load_user_gemini_key(secrets_repo, user_id: str) -> Optional[str]:
    key = await _load_named_key(
        secrets_repo, user_id, "gemini", ("api_key", "key", "GEMINI_API_KEY")
    )
    set_user_gemini_key(key)
    return key


async def load_user_grok_key(secrets_repo, user_id: str) -> Optional[str]:
    key = await _load_named_key(
        secrets_repo, user_id, "grok", ("api_key", "key", "XAI_API_KEY", "GROK_API_KEY")
    )
    set_user_grok_key(key)
    return key


async def load_user_llm_keys(secrets_repo, user_id: str) -> None:
    """Load vault provider credentials into this task's context."""
    _user_id.set(user_id)
    if not secrets_repo or not user_id:
        set_user_gemini_key(None)
        set_user_grok_key(None)
        set_user_groq_key(None)
        set_user_hf_token(None)
        return
    await load_user_gemini_key(secrets_repo, user_id)
    await load_user_grok_key(secrets_repo, user_id)
    groq_key = await _load_named_key(
        secrets_repo, user_id, "groq", ("api_key", "key", "GROQ_API_KEY")
    )
    set_user_groq_key(groq_key)
    hf_token = await _load_named_key(
        secrets_repo, user_id, "huggingface", ("token", "api_key", "key", "HF_TOKEN")
    )
    set_user_hf_token(hf_token)

async def check_user_budget(settings_repo, user_id: str) -> Optional[Dict[str, Any]]:
    """Daily token-budget guardrail (audit §9: cost guardrails with a hard stop).

    Returns the budget dict from context_manager.check_budget, or None when
    budgeting is unavailable. `exceeded` means creation should be refused."""
    if not user_id:
        return None
    try:
        from backend.agents.context_manager import context_manager
        daily_limit = None
        if settings_repo:
            saved = await settings_repo.get_settings(user_id) or {}
            if saved.get("daily_token_limit") is not None:
                daily_limit = int(saved["daily_token_limit"])
        return context_manager.check_budget(user_id, daily_limit=daily_limit)
    except Exception:
        return None

