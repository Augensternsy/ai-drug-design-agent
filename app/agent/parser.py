"""Deterministic natural-language planner for the public Drug Design Agent."""

from __future__ import annotations

import re

from app.config import MAX_NUM_SAMPLES
from app.schemas.api_models import AgentPlan
from app.services.target_service import TargetRegistry


class AgentParseError(ValueError):
    """Raised when a prompt cannot be converted into a safe generation plan."""


def _first_float(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.IGNORECASE)
    return float(match.group(1)) if match else None


def parse_rule_prompt(prompt: str) -> AgentPlan:
    """Parse a concise Chinese or English request without any external service."""
    text = " ".join(prompt.strip().split())
    upper = text.upper()
    if not text:
        raise AgentParseError("请输入分子设计需求。")

    supported = TargetRegistry.get_supported_targets()
    target = next(
        (name for name in supported if re.search(rf"(?<![A-Z0-9]){re.escape(name)}(?![A-Z0-9])", upper)),
        None,
    )
    if target is None:
        raise AgentParseError(
            "未识别到已验证靶点。请明确写出以下之一：" + ", ".join(supported)
        )

    count_patterns = (
        r"(\d+)\s*(?:个|条|molecules?|candidates?)\s*(?:候选)?分子?",
        r"(?:生成|设计|筛选|generate|create)\D{0,18}(\d+)\s*(?:个|条|molecules?|candidates?)?",
    )
    num_samples = 3
    for pattern in count_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            num_samples = int(match.group(1))
            break
    if not 1 <= num_samples <= MAX_NUM_SAMPLES:
        raise AgentParseError(
            f"公开 Demo 每次仅允许生成 1–{MAX_NUM_SAMPLES} 个候选分子。"
        )

    qed_threshold = _first_float(
        r"QED\s*(?:>=|>|至少|不低于|阈值(?:为|=)?)\s*(0(?:\.\d+)?|1(?:\.0+)?)",
        text,
    )
    sa_threshold = _first_float(
        r"SA\s*(?:<=|<|小于|低于|不高于|阈值(?:为|=)?)\s*(\d+(?:\.\d+)?)",
        text,
    )
    if sa_threshold is not None and not 1.0 <= sa_threshold <= 10.0:
        raise AgentParseError("SA 阈值必须位于 1.0–10.0。")

    docking_disabled = bool(re.search(r"(?:不|无需|不要|关闭)\s*(?:进行|执行)?\s*(?:VINA|DOCK(?:ING)?|对接)", upper))
    # Explicit negation wins before the generic keyword check. This prevents
    # the word "Vina" inside "不进行 Vina 对接" from enabling docking.
    run_docking = False if docking_disabled else bool(
        re.search(r"VINA|DOCK(?:ING)?|对接", upper)
    )
    dock_top_k = 1 if run_docking and re.search(r"最优|最佳|TOP\s*1", upper) else None

    return AgentPlan(
        target=target,
        num_samples=num_samples,
        qed_threshold=qed_threshold,
        sa_threshold=sa_threshold,
        qed_priority="QED" in upper or not run_docking,
        run_docking=run_docking,
        dock_top_k=dock_top_k,
        parser="rules",
    )
