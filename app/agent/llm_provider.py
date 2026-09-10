"""Vendor-neutral OpenAI-compatible intent parser with safe rule fallback."""

from __future__ import annotations

import json
import logging
from urllib import error, request

from app.config import (
    LLM_API_KEY,
    LLM_BASE_URL,
    LLM_ENABLED,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    MAX_NUM_SAMPLES,
)
from app.schemas.api_models import AgentPlan
from app.services.target_service import TargetRegistry

logger = logging.getLogger(__name__)


class LLMProviderError(RuntimeError):
    """A sanitized LLM transport or response error safe for internal handling."""


def llm_is_configured() -> bool:
    """Return true only when the optional provider is explicitly enabled."""
    return bool(LLM_ENABLED and LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def chat_completions_url(base_url: str) -> str:
    """Accept either an API base URL or a full chat-completions endpoint."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _extract_content(response_body: object) -> str:
    try:
        content = response_body["choices"][0]["message"]["content"]  # type: ignore[index]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError("LLM response did not contain a chat message") from exc
    if not isinstance(content, str) or not content.strip():
        raise LLMProviderError("LLM response content was empty")
    content = content.strip()
    if content.startswith("```"):
        try:
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        except (IndexError, ValueError) as exc:
            raise LLMProviderError("LLM returned an invalid fenced response") from exc
    return content


def parse_with_llm(prompt: str) -> AgentPlan:
    """Call any OpenAI-compatible endpoint and validate its structured plan."""
    if not llm_is_configured():
        raise LLMProviderError("LLM provider is disabled or incomplete")

    supported = TargetRegistry.get_supported_targets()
    system_prompt = (
        "You are an intent parser, not a molecular model. Return strict JSON only "
        "with keys: target, num_samples, qed_threshold, sa_threshold, "
        "qed_priority, run_docking, dock_top_k. "
        f"target must be one of {supported}; num_samples must be 1-{MAX_NUM_SAMPLES}. "
        "Use null for absent thresholds and dock_top_k. Never add prose."
    )
    payload = json.dumps(
        {
            "model": LLM_MODEL,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    http_request = request.Request(
        chat_completions_url(LLM_BASE_URL),
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(http_request, timeout=LLM_TIMEOUT_SECONDS) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except (error.URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMProviderError("LLM request failed or returned invalid JSON") from exc

    try:
        data = json.loads(_extract_content(response_body))
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM plan was not valid JSON") from exc
    if not isinstance(data, dict):
        raise LLMProviderError("LLM plan must be a JSON object")
    data["target"] = str(data.get("target", "")).upper()
    data["parser"] = "llm"

    # Pydantic is the authority for thresholds, count limits and field types.
    plan = AgentPlan.model_validate(data)
    if plan.target not in supported:
        raise LLMProviderError("LLM selected an unsupported target")
    return plan


def try_parse_with_llm(prompt: str) -> AgentPlan | None:
    """Return None on every provider failure so AgentService can use rules."""
    if not llm_is_configured():
        return None
    try:
        return parse_with_llm(prompt)
    except Exception as exc:
        # Log only the exception class: never log prompts, response bodies or keys.
        logger.warning(
            "LLM plan parsing failed (%s); using rules fallback",
            type(exc).__name__,
        )
        return None
