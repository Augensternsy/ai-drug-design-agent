"""Vendor-neutral OpenAI-compatible intent parser with safe rule fallback."""

from __future__ import annotations

import json
import logging
from urllib import error, request
from urllib.parse import urlsplit, urlunsplit

from pydantic import ValidationError

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


def _safe_base_url(value: str) -> str:
    """Remove query strings and user info before logging a provider URL."""
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError:
        return "<invalid>"
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))


def _safe_error_fields(raw: bytes) -> tuple[bool, str, str, str]:
    """Extract bounded error metadata without logging credentials or prompts."""
    try:
        body = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False, "unknown", "unknown", "unavailable"
    error_body = body.get("error", body) if isinstance(body, dict) else {}
    if not isinstance(error_body, dict):
        return True, "unknown", "unknown", "unavailable"

    def safe_value(key: str) -> str:
        value = " ".join(str(error_body.get(key, "unknown")).split())[:240]
        if LLM_API_KEY:
            value = value.replace(LLM_API_KEY, "[REDACTED]")
        return value

    return True, safe_value("code"), safe_value("type"), safe_value("message")


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
            http_status = getattr(response, "status", 200)
            raw_response = response.read()
    except error.HTTPError as exc:
        response_is_json, error_code, error_type, error_message = _safe_error_fields(
            exc.read()
        )
        logger.warning(
            "LLM request failed http_status=%s response_json=%s "
            "error_code=%s error_type=%s error_message=%s",
            exc.code,
            str(response_is_json).lower(),
            error_code,
            error_type,
            error_message,
        )
        raise LLMProviderError(f"http_status_{exc.code}") from exc
    except TimeoutError as exc:
        raise LLMProviderError("timeout") from exc
    except error.URLError as exc:
        reason = "timeout" if isinstance(exc.reason, TimeoutError) else "network_error"
        raise LLMProviderError(reason) from exc

    try:
        response_body = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LLMProviderError("response_json_invalid") from exc
    logger.info(
        "LLM request completed http_status=%s response_json=true "
        "response_bytes=%s model=%s",
        http_status,
        len(raw_response),
        LLM_MODEL,
    )

    try:
        data = json.loads(_extract_content(response_body))
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM plan was not valid JSON") from exc
    if not isinstance(data, dict):
        raise LLMProviderError("LLM plan must be a JSON object")
    data["target"] = str(data.get("target", "")).upper()
    data["parser"] = "llm"

    # Pydantic is the authority for thresholds, count limits and field types.
    try:
        plan = AgentPlan.model_validate(data)
    except ValidationError as exc:
        raise LLMProviderError("agent_plan_validation_failed") from exc
    if plan.target not in supported:
        raise LLMProviderError("LLM selected an unsupported target")
    return plan


def try_parse_with_llm(prompt: str) -> AgentPlan | None:
    """Return None on every provider failure so AgentService can use rules."""
    logger.info(
        "LLM config enabled=%s base_url=%s LLM_API_KEY_PRESENT=%s model=%s",
        str(LLM_ENABLED).lower(),
        _safe_base_url(LLM_BASE_URL),
        str(bool(LLM_API_KEY)).lower(),
        LLM_MODEL or "<unset>",
    )
    if not llm_is_configured():
        logger.warning("LLM fallback_reason=configuration_incomplete")
        return None
    try:
        return parse_with_llm(prompt)
    except Exception as exc:
        # Log only sanitized diagnostics: never log prompts, raw bodies or keys.
        reason = str(exc) if isinstance(exc, LLMProviderError) else type(exc).__name__
        logger.warning("LLM fallback_reason=%s", reason)
        return None
