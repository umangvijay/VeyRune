"""Shared Gemini client — real model calls, config-driven model names."""

import asyncio
import contextvars
import json
from contextlib import asynccontextmanager
import logging
import re
from typing import Any, Optional, Type

from backend.config.settings import settings
from backend.services.llm_context import effective_gemini_key, effective_groq_key, effective_grok_key, effective_hf_token, get_user_id

logger = logging.getLogger(__name__)


class GeminiQuotaExceeded(RuntimeError):
    """Raised when the configured Gemini key hits RESOURCE_EXHAUSTED / 429."""


def is_quota_error(exc: BaseException) -> bool:
    """True only for quota exhaustion, which may justify a provider fallback."""
    msg = str(exc)
    lowered = msg.lower()
    return any(
        s in msg
        for s in (
            "RESOURCE_EXHAUSTED",
            "quota exhausted",
        )
    ) or "429" in msg or "quota" in lowered


def is_retryable_model_error(exc: BaseException) -> bool:
    """Quota, missing model, or transient Gemini failures — try the next model."""
    # Credentials and project/model permissions are not model-specific. Cycling
    # through every fallback ID only repeats a doomed request and burns latency.
    if is_auth_error(exc):
        return False
    if is_quota_error(exc) or isinstance(exc, GeminiQuotaExceeded):
        return True
    msg = str(exc)
    lowered = msg.lower()
    return any(
        s in msg
        for s in ("NOT_FOUND", "UNAVAILABLE", "overloaded")
    ) or any(
        s in lowered
        for s in ("not found", "not supported", "unknown model", "invalid model")
    )



def is_auth_error(exc: BaseException) -> bool:
    """True when the credential itself is rejected (revoked/expired key)."""
    msg = str(exc)
    return (
        "UNAUTHENTICATED" in msg
        or "API_KEY_INVALID" in msg
        or "PERMISSION_DENIED" in msg
        or "API key not valid" in msg
        or "ACCESS_TOKEN_TYPE_UNSUPPORTED" in msg
        or "401" in msg
    )


async def probe_key_status() -> dict:
    """Classify the configured LLM credential at startup.
    Returns a credential/configuration status. A successful catalog request is
    deliberately not reported as inference-ready; generation is not exercised
    during startup because that can incur cost and delay cold starts.
    """
    import os
    from backend.services.llm_context import active_llm_provider
    provider = active_llm_provider()
    key = (os.environ.get("GEMINI_API_KEY") or settings.GEMINI_API_KEY or "").strip()
    groq_key = (os.environ.get("GROQ_API_KEY") or settings.GROQ_API_KEY or "").strip()
    hf_token = effective_hf_token()
    project = (os.environ.get("GOOGLE_CLOUD_PROJECT") or settings.GOOGLE_CLOUD_PROJECT or "").strip()
    if provider == "groq":
        if not groq_key:
            return {"status": "missing", "detail": "LLM_PROVIDER=groq but GROQ_API_KEY is not configured."}
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {groq_key}"},
                )
            if resp.status_code == 200:
                return {"status": "catalog_ok", "detail": "Groq accepted the key for model discovery; inference is verified only by a live agent run."}
            return {"status": "invalid", "detail": f"Groq credential check failed (HTTP {resp.status_code})."}
        except Exception as e:
            logger.warning("Groq credential probe failed (%s)", type(e).__name__)
            return {"status": "unknown", "detail": "Could not reach Groq. Check network access and provider configuration."}
    if provider == "huggingface":
        if not hf_token:
            return {"status": "missing", "detail": "LLM_PROVIDER=huggingface but HF_TOKEN is not configured."}
        return {"status": "configured", "detail": "Hugging Face token is configured; inference is verified only by a live model request."}
    if provider == "gemini" and key:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    headers={"x-goog-api-key": key},
                )
            if resp.status_code == 200:
                return {
                    "status": "catalog_ok",
                    "detail": "Key is accepted for model discovery; text generation has not been verified.",
                }
            if resp.status_code in (400, 401, 403):
                return {"status": "invalid", "detail": f"Gemini rejected the configured key (HTTP {resp.status_code}). Add a fresh key from aistudio.google.com/apikey in Settings."}
            return {"status": "invalid", "detail": f"Gemini key check failed (HTTP {resp.status_code})."}
        except Exception as e:
            # HTTP client errors can include endpoint URLs (including query-key
            # credentials) and cloud project details. Expose only the category.
            logger.warning("Gemini credential probe failed (%s)", type(e).__name__)
            return {"status": "unknown", "detail": "Could not reach Gemini. Check network access and provider configuration."}
    if provider == "vertex" and project:
        # Project identifiers are infrastructure details; never expose them from
        # a health/capability response.
        return {"status": "vertex", "detail": "Using Vertex AI (project configured)"}
    return {"status": "missing", "detail": "No GEMINI_API_KEY and no GOOGLE_CLOUD_PROJECT configured. Add a key in Settings."}


FLASH_MODELS = (
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
)


def _is_allowed_flash(model: str) -> bool:
    """Flash-tier models used for routine work. Never Pro or Reasoning."""
    name = (model or "").strip().lower()
    return name in FLASH_MODELS


def _is_gemini_35_or_newer(model: str) -> bool:
    return _is_allowed_flash(model)


def allowed_models() -> list[str]:
    from backend.services.llm_context import active_llm_provider
    if active_llm_provider() == "huggingface":
        return [settings.HF_MODEL]
    return list(dict.fromkeys(m.strip() for m in settings.GEMINI_ALLOWED_MODELS.split(",") if m.strip()))


def _candidate_models(preferred: Optional[str] = None) -> list:
    from backend.services.llm_context import get_user_model
    explicit = preferred or get_user_model()
    if explicit:
        if explicit not in allowed_models():
            raise ValueError("Selected model is not enabled on this server")
        # An explicit selection must not silently run on a different model.
        return [explicit]
    return list(dict.fromkeys(m for m in (settings.GEMINI_MODEL, *FLASH_MODELS) if m in allowed_models()))


def candidate_models(preferred: Optional[str] = None) -> list:
    """Models to try for the active shared provider, without retrying an alias as another model."""
    from backend.services.llm_context import active_llm_provider
    if active_llm_provider() == "groq":
        if preferred and preferred != settings.GROQ_MODEL:
            raise ValueError("A Gemini model was selected, but only Groq is configured")
        return [settings.GROQ_MODEL]
    if active_llm_provider() == "huggingface":
        if preferred and preferred != settings.HF_MODEL:
            raise ValueError("A Gemini model was selected, but only Hugging Face is configured")
        return [settings.HF_MODEL]
    return _candidate_models(preferred)


async def run_adk_debug(build_agent, prompt: str, app_name: Optional[str] = None):
    """Run an ADK InMemoryRunner, retrying Flash model IDs on NOT_FOUND / quota."""
    from google.adk.runners import InMemoryRunner

    last: Optional[Exception] = None
    for model in candidate_models():
        try:
            agent = build_agent(model)
            runner = InMemoryRunner(agent=agent, app_name=app_name or settings.APP_NAME)
            return await runner.run_debug(prompt)
        except Exception as e:
            last = e
            if is_retryable_model_error(e):
                logger.warning("ADK Gemini %s unavailable (%s); trying next Flash model", model, e)
                continue
            raise
    raise last or RuntimeError("ADK runner produced no events")


def _client():
    from google import genai

    from backend.services.llm_context import active_llm_provider
    key = effective_gemini_key()
    if active_llm_provider() != "vertex" and key:
        return genai.Client(api_key=key)
    return genai.Client(
        vertexai=True,
        project=settings.GOOGLE_CLOUD_PROJECT,
        location=settings.GOOGLE_CLOUD_REGION,
    )


async def _generate_content_async(client, **kwargs):
    """Run the sync Gemini SDK off the event loop so workflows can still be polled."""
    return await asyncio.to_thread(client.models.generate_content, **kwargs)


async def _grok_complete(prompt: str, *, json_mode: bool = False) -> str:
    """xAI OpenAI-compatible chat. Used only after Gemini is unavailable."""
    key = effective_grok_key()
    if not key:
        raise GeminiQuotaExceeded(
            "Gemini quota exhausted and no Grok key is configured. Add a Gemini or xAI key in Settings."
        )
    import httpx

    payload: dict = {
        "model": settings.GROK_MODEL or "grok-4-fast",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1 if json_mode else 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Grok HTTP {response.status_code}: {response.text[:400]}")
        data = response.json()
    text = (
        ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    ).strip()
    if not text:
        raise ValueError("Grok returned an empty response")
    logger.info("LLM used Grok fallback model %s", payload["model"])
    return text


async def _groq_complete(prompt: str, *, json_mode: bool = False) -> str:
    """Groq OpenAI-compatible fallback. Never include provider response bodies in errors."""
    key = effective_groq_key()
    if not key:
        raise RuntimeError("No Groq API key is configured")
    import httpx

    payload: dict = {
        "model": settings.GROQ_MODEL or "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1 if json_mode else 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Groq HTTP {response.status_code}")
        data = response.json()
    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise ValueError("Groq returned an empty response")
    logger.info("LLM used Groq fallback model %s", payload["model"])
    return text


async def _huggingface_complete(prompt: str, *, json_mode: bool = False, model: Optional[str] = None) -> str:
    """Call the Hugging Face OpenAI-compatible inference router without logging secrets."""
    key = effective_hf_token()
    if not key:
        raise RuntimeError("No Hugging Face token is configured")
    import httpx

    payload: dict = {
        "model": model or settings.HF_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1 if json_mode else 0.2,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        response = await client.post(
            "https://router.huggingface.co/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code >= 400:
            if response.status_code == 402:
                raise RuntimeError("Hugging Face inference credits or billing are unavailable (HTTP 402)")
            if response.status_code == 403:
                raise RuntimeError("Hugging Face token lacks Inference Providers access (HTTP 403)")
            if response.status_code == 401:
                raise RuntimeError("Hugging Face rejected the configured token (HTTP 401)")
            raise RuntimeError(f"Hugging Face inference failed (HTTP {response.status_code})")
        data = response.json()
    text = (((data.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not text:
        raise ValueError("Hugging Face returned an empty response")
    logger.info("LLM used Hugging Face model %s", payload["model"])
    return text


def _groq_is_only_configured_provider() -> bool:
    """True when Groq is the explicitly selected or auto-detected provider."""
    from backend.services.llm_context import active_llm_provider
    return active_llm_provider() == "groq"


def _huggingface_is_only_configured_provider() -> bool:
    from backend.services.llm_context import active_llm_provider
    return active_llm_provider() == "huggingface"


def _coerce_json(text: str) -> Any:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if starts:
        start = min(starts)
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            text = text[start : end + 1]
    text = re.sub(r",\s*([}\]])", r"\1", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text, strict=False)



MAX_OUTPUT_RESERVE_TOKENS = 8192  # reserved headroom per paid call

_active_reservation: "contextvars.ContextVar[Optional[dict]]" = contextvars.ContextVar("budget_reservation", default=None)

@asynccontextmanager
async def _budget_reservation(prompt: str):
    """Atomic budget reservation (v5.6 A3): reserve the estimated MAXIMUM
    before the paid call, settle the actual after. Two processes racing near
    the cap cannot both admit work — the guard is a single guarded upsert."""
    user_id = get_user_id()
    from backend.config.settings import settings as app_settings
    from backend.repositories.usage_repository import get_usage_repo, today_utc
    repo = get_usage_repo()
    if not user_id or repo is None:
        yield None
        return
    est_in = (len(prompt or "") + 3) // 4
    est_max = est_in + app_settings.MAX_OUTPUT_RESERVE_TOKENS
    ok = await repo.reserve_usage(user_id, today_utc(), est_max,
                                  cap=app_settings.DEFAULT_DAILY_TOKEN_LIMIT)
    if not ok:
        raise GeminiQuotaExceeded(
            "Daily token budget exhausted (reservation refused). "
            "Raise the limit in Settings or wait for the window to reset."
        )
    state = {"reserved": est_max, "actual": 0}
    token = _active_reservation.set(state)
    try:
        yield state
    finally:
        _active_reservation.reset(token)
        try:
            await repo.settle_usage(user_id, today_utc(), state["reserved"], state["actual"])
        except Exception:
            logger.exception("Budget settlement failed for %s", user_id)


def _record_usage_estimate(prompt: str, output: str) -> None:
    """Record an estimated token spend for the user (4 chars/token), so the
    daily budget check in workflow creation actually has data. The budget is
    a cost guardrail, not billing. Never raises.

    Two books are kept: the process-local ContextManager (fast, per-request)
    and the durable usage ledger (audit F08) so the daily cap holds across
    API/worker processes and restarts."""
    try:
        user_id = get_user_id()
        if not user_id:
            return
        from backend.agents.context_manager import context_manager
        inp = max(0, (len(prompt or "") + 3) // 4)
        out = max(0, (len(output or "") + 3) // 4)
        total = inp + out
        context_manager.record_usage(user_id, inp, out)
        # With an open reservation, the settle path counts the actual spend
        # (releasing the unused hold). Without one, record durably — committed.
        reservation = _active_reservation.get()
        if reservation is not None:
            reservation["actual"] = max(reservation["actual"], total)
        elif total > 0:
            import asyncio
            from backend.repositories.usage_repository import record_usage_durably
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(record_usage_durably(user_id, total))
    except Exception:
        logger.debug("usage estimate recording failed", exc_info=True)


async def _generate_text_unreserved(prompt: str, model: Optional[str] = None) -> str:
    if _huggingface_is_only_configured_provider():
        return await _huggingface_complete(prompt, json_mode=False, model=model)
    if not model and _groq_is_only_configured_provider():
        return await _groq_complete(prompt, json_mode=False)
    from google.genai import types

    last: Optional[Exception] = None
    quota_hits = 0
    for candidate in _candidate_models(model):
        try:
            client = _client()
            response = await _generate_content_async(
                client,
                model=candidate,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            text = (response.text or "").strip()
            if text:
                if candidate != (model or settings.GEMINI_MODEL):
                    logger.info("Gemini text used fallback model %s", candidate)
                _record_usage_estimate(prompt, text)
                return text
            last = ValueError(f"empty response from {candidate}")
        except Exception as e:
            last = e
            if is_retryable_model_error(e):
                logger.warning("Gemini model %s unavailable (%s); trying another", candidate, e)
                if is_quota_error(e) or isinstance(e, GeminiQuotaExceeded):
                    quota_hits += 1
                    if quota_hits >= 3:
                        break
                continue
            raise
    from backend.services.llm_context import get_user_model
    if (model or get_user_model()) and last:
        raise last
    if last and is_quota_error(last):
        try:
            _t = await _groq_complete(prompt, json_mode=False)
            _record_usage_estimate(prompt, _t)
            return _t
        except Exception as groq_err:
            logger.warning("Groq text fallback failed (%s)", type(groq_err).__name__)
        try:
            _t = await _grok_complete(prompt, json_mode=False)
            _record_usage_estimate(prompt, _t)
            return _t
        except Exception as grok_err:
            logger.warning("Grok text fallback failed: %s", grok_err)
        raise GeminiQuotaExceeded(
            "Gemini quota exhausted. Add a Gemini, Groq, or xAI key in Settings."
        ) from last
    try:
        _t = await _groq_complete(prompt, json_mode=False)
        _record_usage_estimate(prompt, _t)
        return _t
    except Exception as groq_err:
        logger.warning("Groq text fallback failed (%s)", type(groq_err).__name__)
    try:
        return await _grok_complete(prompt, json_mode=False)
    except Exception:
        raise last or GeminiQuotaExceeded("Gemini quota exhausted. Add your own key in Settings.")


async def _generate_json_unreserved(prompt: str, schema: Optional[Type] = None, model: Optional[str] = None) -> Any:
    if _huggingface_is_only_configured_provider():
        return _coerce_json(await _huggingface_complete(prompt, json_mode=True, model=model))
    if not model and _groq_is_only_configured_provider():
        return _coerce_json(await _groq_complete(prompt, json_mode=True))
    from google.genai import types

    last: Optional[Exception] = None
    quota_hits = 0
    for candidate in _candidate_models(model):
        try:
            client = _client()
            config_kwargs = {
                "response_mime_type": "application/json",
                "temperature": 0.1,
                "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
            }
            if schema is not None:
                config_kwargs["response_schema"] = schema
            response = await _generate_content_async(
                client,
                model=candidate,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            text = (response.text or "").strip()
            if not text:
                raise ValueError("Model returned empty JSON")
            try:
                parsed = _coerce_json(text)
            except json.JSONDecodeError:
                logger.warning("Model JSON was invalid; requesting a repaired payload")
                fixed = await generate_text(
                    "Fix this into valid JSON only. Escape quotes and newlines inside strings. "
                    "No markdown fences.\n\n" + text[:24000],
                    model=candidate,
                )
                parsed = _coerce_json(fixed)
            if candidate != (model or settings.GEMINI_MODEL):
                logger.info("Gemini JSON used fallback model %s", candidate)
            _record_usage_estimate(prompt, text)
            return parsed
        except Exception as e:
            last = e
            if is_retryable_model_error(e):
                logger.warning("Gemini model %s unavailable (%s); trying another", candidate, e)
                if is_quota_error(e) or isinstance(e, GeminiQuotaExceeded):
                    quota_hits += 1
                    if quota_hits >= 3:
                        break
                continue
            logger.warning("Gemini JSON failed on %s (%s); trying another", candidate, e)
            continue
    from backend.services.llm_context import get_user_model
    if (model or get_user_model()) and last:
        raise last
    if last and (is_quota_error(last) or isinstance(last, GeminiQuotaExceeded)):
        try:
            _t = await _groq_complete(prompt, json_mode=True)
            _record_usage_estimate(prompt, str(_t))
            return _coerce_json(_t)
        except Exception as groq_err:
            logger.warning("Groq JSON fallback failed (%s)", type(groq_err).__name__)
        try:
            _t = await _grok_complete(prompt, json_mode=True)
            _record_usage_estimate(prompt, str(_t))
            return _coerce_json(_t)
        except Exception as grok_err:
            logger.warning("Grok JSON fallback failed: %s", grok_err)
        raise GeminiQuotaExceeded(
            "Gemini quota exhausted. Add a Groq or xAI key as a fallback."
        ) from last
    try:
        return _coerce_json(await _groq_complete(prompt, json_mode=True))
    except Exception as groq_err:
        logger.warning("Groq JSON fallback failed (%s)", type(groq_err).__name__)
    try:
        return _coerce_json(await _grok_complete(prompt, json_mode=True))
    except Exception:
        raise last or ValueError("Model returned empty JSON")


async def describe_image(image_bytes: bytes, mime: str = "image/jpeg", name: str = "photo") -> str:
    """Describe an attached photo so the planner can use it."""
    from google.genai import types

    part = None
    if hasattr(types.Part, "from_bytes"):
        part = types.Part.from_bytes(data=image_bytes, mime_type=mime or "image/jpeg")
    else:
        part = types.Part(inline_data=types.Blob(data=image_bytes, mime_type=mime or "image/jpeg"))
    contents = [
        part,
        (
            f"Describe this attached photo ({name}) for an automation agent. "
            "Extract visible text, UI labels, URLs, tables, and what the user likely wants done."
        ),
    ]
    last: Optional[Exception] = None
    for candidate in _candidate_models():
        try:
            client = _client()
            response = await _generate_content_async(
                client,
                model=candidate,
                contents=contents,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                ),
            )
            return (response.text or f"A photo named {name} was attached.").strip()
        except Exception as e:
            last = e
            if is_retryable_model_error(e):
                logger.warning("Image describe Gemini %s unavailable (%s)", candidate, e)
                continue
            break
    e = last
    if e and is_quota_error(e):
        try:
            return await _grok_complete(
                f"Describe this attached photo ({name}) for an automation agent from the filename and mime type {mime}. "
                "The image bytes could not be sent to Gemini. Say that a photo was attached and what the user likely wants.",
                json_mode=False,
            )
        except Exception:
            raise GeminiQuotaExceeded(
                "Gemini quota exhausted. Add your own key in Settings."
            ) from e
    if e:
        logger.warning("Image describe failed: %s", e)
    return f"A photo named {name} was attached."


async def search_web(query: str) -> list[dict]:
    """Discover sources through Google Search grounding metadata."""
    from google.genai import types
    response = await _generate_content_async(
        _client(), model=candidate_models()[0], contents=query,
        config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]),
    )
    sources = {}
    for candidate in response.candidates or []:
        grounding = getattr(candidate, "grounding_metadata", None)
        for chunk in getattr(grounding, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            uri = getattr(web, "uri", None)
            if uri and uri.startswith("https://"):
                sources[uri] = {"url": uri, "title": getattr(web, "title", "") or "", "snippet": ""}
    if not sources:
        raise RuntimeError("Search returned no grounded sources; research cannot be verified")
    return list(sources.values())


async def generate_text(prompt: str, model: Optional[str] = None) -> str:
    """Public entry: every paid call runs inside an atomic budget reservation
    (reserve estimated max → run → settle actual)."""
    async with _budget_reservation(prompt):
        return await _generate_text_unreserved(prompt, model=model)


async def generate_json(prompt: str, schema: Optional[Type] = None, model: Optional[str] = None) -> Any:
    async with _budget_reservation(prompt):
        return await _generate_json_unreserved(prompt, schema=schema, model=model)
