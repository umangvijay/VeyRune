"""Google ADK bridge to Hugging Face's OpenAI-compatible inference router."""

import json
import logging
from typing import AsyncGenerator

import httpx
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from backend.config.settings import settings
from backend.services.groq_adk import GroqADK, _request_messages, _request_tools, _response_schema
from backend.services.llm_context import effective_hf_token

logger = logging.getLogger(__name__)


class HuggingFaceADK(GroqADK):
    """ADK model adapter supporting planner schemas and real function/tool calls."""

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        token = effective_hf_token()
        if not token:
            raise RuntimeError("Hugging Face provider selected but HF_TOKEN is not configured")

        config = llm_request.config
        model = self.model or settings.HF_MODEL
        payload: dict = {
            "model": model,
            "messages": _request_messages(llm_request),
        }
        temperature = getattr(config, "temperature", None) if config else None
        if temperature is not None:
            payload["temperature"] = temperature
        tools = _request_tools(llm_request)
        if tools:
            payload["tools"] = tools
        schema = _response_schema(config) if config else None
        if schema and not tools:
            payload["response_format"] = {"type": "json_schema", "json_schema": schema}
        elif config and getattr(config, "response_mime_type", None) == "application/json":
            payload["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
            response = await client.post(
                "https://router.huggingface.co/v1/chat/completions",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json=payload,
            )
        if response.status_code >= 400:
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after") if response.headers else None
                suffix = f"; retry after {retry_after}s" if retry_after and retry_after.isdigit() else ""
                raise RuntimeError(f"Hugging Face inference rate limit reached (HTTP 429{suffix})")
            if response.status_code == 402:
                raise RuntimeError("Hugging Face inference credits or billing are unavailable (HTTP 402)")
            if response.status_code == 403:
                raise RuntimeError("Hugging Face token lacks Inference Providers access (HTTP 403)")
            if response.status_code == 401:
                raise RuntimeError("Hugging Face rejected the configured token (HTTP 401)")
            raise RuntimeError(f"Hugging Face inference failed (HTTP {response.status_code})")

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        parts = []
        if message.get("content"):
            parts.append(types.Part(text=message["content"]))
        for call in message.get("tool_calls") or []:
            fn = call.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise ValueError("Hugging Face returned invalid JSON for a tool call") from exc
            parts.append(types.Part(function_call=types.FunctionCall(
                id=call.get("id"), name=fn.get("name"), args=args,
            )))
        if not parts:
            raise ValueError("Hugging Face returned an empty model response")

        logger.info("ADK model call completed with Hugging Face model %s", model)
        yield LlmResponse(
            content=types.Content(role="model", parts=parts),
            model_version=model,
            partial=False,
        )
