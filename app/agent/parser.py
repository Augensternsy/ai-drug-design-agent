"""
Agent Natural Language Intent & Parameter Parser Module.
Parses natural language prompts into target, num_samples, and run_docking parameters.
Supports LLM-based intent parsing when LLM_ENABLED is true.
"""
import re
import json
import os
import requests
import logging
from typing import Dict, Any, Optional
from app.schemas.api_models import AgentIntentParseResult
from app.config import LLM_ENABLED, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger("agent_parser")

TARGET_ALIASES: Dict[str, list] = {
    "ESR1": ["ESR1", "雌激素受体1", "雌激素受体", "雌激素受体ESR1", "esr1"],
    "HCRTR1": ["HCRTR1", "食欲素受体1(HCRTR1)", "食欲素受体1", "食欲素受体", "hcrtr1"],
    "JAK1": ["JAK1", "JAK1激酶", "JAK1蛋白", "jak1"],
    "P2RX3": ["P2RX3", "P2X3受体(P2RX3)", "P2X3受体", "P2X3", "p2rx3"],
    "KDM1A": ["KDM1A", "去甲基化酶KDM1A", "KDM1A蛋白", "kdm1a"],
    "IDH1": ["IDH1", "异柠檬酸脱氢酶1(IDH1)", "异柠檬酸脱氢酶1", "IDH1靶点", "idh1"],
    "RIOK1": ["RIOK1", "RIOK1激酶", "RIOK1蛋白", "riok1"],
    "NR4A1": ["NR4A1", "核受体NR4A1", "NR4A1蛋白", "nr4a1"],
    "GRIK1": ["GRIK1", "谷氨酸受体GRIK1", "GRIK1蛋白", "grik1"],
    "CCR9": ["CCR9", "趋化因子受体CCR9", "CCR9蛋白", "ccr9"],
    "FTO": ["FTO", "FTO去甲基化酶", "FTO蛋白", "fto"],
    "SPIN1": ["SPIN1", "SPIN1蛋白", "spin1"]
}

ALL_ALIAS_STRINGS = []
for aliases in TARGET_ALIASES.values():
    ALL_ALIAS_STRINGS.extend(aliases)
ALL_ALIAS_STRINGS.sort(key=len, reverse=True)


class AgentIntentParser:
    """
    Agent Natural Language Intent & Parameter Parser Engine.
    Parses natural language user prompts into canonical target, num_samples, and run_docking parameters.
    """

    NO_DOCK_KEYWORDS = [
        "跳过vina", "跳过 vina", "跳过", "跳过对接", "无需对接", "不需要分子对接",
        "不跑对接", "不跑vina", "without docking", "without vina", "no docking",
        "skip docking", "skip vina", "仅评估理化性质", "不对接", "免对接",
        "无需vina", "不需要vina", "不进行对接", "不进行分子对接", "不执行对接",
        "不执行vina", "不执行分子对接"
    ]

    NO_DOCK_REGEX = re.compile(
        r'(跳过|无需|不需要|不跑|不进行|不执行|免|without|skip|no)\s*(vina|对接|分子对接|3d对接)?',
        re.IGNORECASE
    )

    @classmethod
    def parse_prompt(cls, user_input: str) -> AgentIntentParseResult:
        prompt = user_input.strip()

        # Print/log LLM configuration status
        api_key_present = bool(LLM_API_KEY and LLM_API_KEY.strip())
        log_msg = f"LLM config enabled={LLM_ENABLED} model={LLM_MODEL} LLM_API_KEY_PRESENT={api_key_present}"
        logger.info(log_msg)
        print(f"[AgentIntentParser] {log_msg}")

        if LLM_ENABLED and api_key_present:
            llm_res = cls._parse_with_llm(prompt)
            if llm_res:
                return llm_res

        return cls._parse_with_rules(prompt)

    @classmethod
    def _parse_with_llm(cls, prompt: str) -> Optional[AgentIntentParseResult]:
        url = f"{LLM_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {LLM_API_KEY}",
            "Content-Type": "application/json"
        }
        system_prompt = (
            "You are an AI drug design intent parser. Extract parameters from user request into JSON with keys:\n"
            "- \"target\": string (Must be canonical target symbol: ESR1, HCRTR1, JAK1, P2RX3, KDM1A, IDH1, RIOK1, NR4A1, GRIK1, CCR9, FTO, SPIN1)\n"
            "- \"num_samples\": integer (1 to 5)\n"
            "- \"run_docking\": boolean (false if user explicitly asks to skip docking/vina/3D docking, otherwise true)\n"
            "Return JSON object only."
        )
        data = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            resp = requests.post(url, headers=headers, json=data, timeout=8)
            if resp.status_code == 200:
                res_json = resp.json()
                content = res_json["choices"][0]["message"]["content"]
                parsed = json.loads(content)

                target_raw = str(parsed.get("target", "ESR1")).strip()
                canonical_target = "ESR1"
                for canonical, aliases in TARGET_ALIASES.items():
                    if target_raw.upper() == canonical or any(a.lower() == target_raw.lower() for a in aliases):
                        canonical_target = canonical
                        break

                num_samples = int(parsed.get("num_samples", 3))
                num_samples = min(max(num_samples, 1), 5)

                run_docking = bool(parsed.get("run_docking", True))

                return AgentIntentParseResult(
                    parser="llm",
                    target=canonical_target,
                    num_samples=num_samples,
                    run_docking=run_docking,
                    raw_prompt=prompt
                )
            else:
                logger.warning(f"LLM API request failed with status {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"LLM parser exception: {e}")

        return None

    @classmethod
    def _parse_with_rules(cls, user_input: str) -> AgentIntentParseResult:
        prompt = user_input.strip()
        prompt_lower = prompt.lower()

        # 1. Target Recognition
        parsed_target = None
        for canonical_name, aliases in TARGET_ALIASES.items():
            for alias in aliases:
                if alias.lower() in prompt_lower:
                    parsed_target = canonical_name
                    break
            if parsed_target:
                break

        if not parsed_target:
            parsed_target = "ESR1"  # Default fallback

        # 2. Docking Requirement Recognition
        run_docking = True
        for kw in cls.NO_DOCK_KEYWORDS:
            if kw in prompt_lower:
                run_docking = False
                break
        if run_docking and cls.NO_DOCK_REGEX.search(prompt_lower):
            run_docking = False

        # 3. Number of Samples Recognition
        prompt_clean = prompt
        for alias in ALL_ALIAS_STRINGS:
            prompt_clean = re.sub(re.escape(alias), '', prompt_clean, flags=re.I)
        prompt_clean = re.sub(r'ESR1|HCRTR1|JAK1|P2RX3|KDM1A|IDH1|RIOK1|NR4A1|GRIK1|CCR9|FTO|SPIN1|P2X3', '', prompt_clean, flags=re.I)
        prompt_clean = re.sub(r'3D|3d|vina', '', prompt_clean, flags=re.I)

        cn_num_words = [
            (5, ["5", "五个", "五条", "五", "五个候选分子"]),
            (4, ["4", "四个", "四条", "四"]),
            (3, ["3", "三个", "三条", "三", "3候选分子"]),
            (2, ["2", "两个", "两条", "两", "双候选", "双"]),
            (1, ["1", "一个", "一条", "一", "single", "单"])
        ]

        num_samples = None
        match_num = re.search(r'(\d+)\s*(个|条|候选分子|分子|分子项)?', prompt_clean)
        if match_num:
            num_samples = min(max(int(match_num.group(1)), 1), 5)
        else:
            for val, words in cn_num_words:
                for w in words:
                    if w in prompt_clean.lower():
                        num_samples = val
                        break
                if num_samples:
                    break

        if not num_samples:
            num_samples = 3

        return AgentIntentParseResult(
            parser="rules",
            target=parsed_target,
            num_samples=num_samples,
            run_docking=run_docking,
            raw_prompt=prompt
        )


def parse_agent_intent_and_params(user_input: str) -> Dict[str, Any]:
    """
    Backward-compatible dictionary helper for agent intent & parameter parsing.
    """
    res = AgentIntentParser.parse_prompt(user_input)
    return {
        "parser": res.parser,
        "target": res.target,
        "num_samples": res.num_samples,
        "run_docking": res.run_docking
    }
