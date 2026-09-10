"""Optional OpenAI-compatible intent parser with deterministic fallback."""

from __future__ import annotations

import json
import logging
from urllib import error, request

from app.config import (
    LLM_API_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
    MAX_NUM_SAMPLES,
)
from app.schemas.api_models import AgentPlan
from app.services.target_service import TargetRegistry

logger = logging.getLogger(__name__)


def llm_is_configured() -> bool:
    return bool(
        LLM_PROVIDER == "openai_compatible"
        and LLM_API_BASE_URL
        and LLM_API_KEY
        and LLM_MODEL
    )


def parse_with_llm(prompt: str) -> AgentPlan:
    """Return a validated plan from an OpenAI-compatible chat completion API."""
    if not llm_is_configured():
        raise RuntimeError("LLM provider is not configured")

    supported = TargetRegistry.get_supported_targets()
    system_prompt = (
        "Extract a drug-design plan as strict JSON with keys: target, num_samples, "
        "qed_threshold, sa_threshold, qed_priority, run_docking, dock_top_k. "
        f"target must be one of {supported}; num_samples must be 1-{MAX_NUM_SAMPLES}. "
        "Use null for absent thresholds and dock_top_k. Do not add prose."
    )
    payload = json.dumps(
        {
            "model": LLM_MODEL,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
    ).encode("utf-8")
    endpoint = f"{LLM_API_BASE_URL}/chat/completions"
    http_request = request.Request(
        endpoint,
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
    except (error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM intent parsing failed: {exc}") from exc

    content = response_body["choices"][0]["message"]["content"].strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    data = json.loads(content)
    data["target"] = str(data.get("target", "")).upper()
    data["parser"] = "llm"
    plan = AgentPlan.model_validate(data)
    if plan.target not in supported:
        raise ValueError(f"Unsupported target from LLM: {plan.target}")
    return plan


def try_parse_with_llm(prompt: str) -> AgentPlan | None:
    if not llm_is_configured():
        return None
    try:
        return parse_with_llm(prompt)
    except Exception as exc:
        logger.warning("LLM parser unavailable; using deterministic fallback: %s", exc)
        return None
