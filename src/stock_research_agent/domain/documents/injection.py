"""Deterministic markers for untrusted instruction-like document text."""

from __future__ import annotations

import re

from stock_research_agent.domain.documents.enums import SafetyMarker

RULESET_VERSION = "prompt-injection-rules-v1"
_RULES: tuple[tuple[SafetyMarker, re.Pattern[str]], ...] = (
    (
        SafetyMarker.PROMPT_INJECTION_CANDIDATE,
        re.compile(
            r"ignore\s+(?:all\s+)?previous\s+instructions|"
            r"忽略(?:之前|以上).{0,8}指令|无视(?:所有|全部).{0,8}(?:规则|指令)",
            re.I,
        ),
    ),
    (SafetyMarker.SYSTEM_PROMPT_IMITATION, re.compile(r"system\s*prompt|系统提示词", re.I)),
    (
        SafetyMarker.CREDENTIAL_REQUEST,
        re.compile(r"(?:reveal|show|发送|提供).{0,24}(?:api.?key|password|token|密钥|密码)", re.I),
    ),
    (
        SafetyMarker.TOOL_INVOCATION_TEXT,
        re.compile(r"(?:tool|function)[_. -]?(?:call|use)|调用工具", re.I),
    ),
    (
        SafetyMarker.EXFILTRATION_URL,
        re.compile(r"https?://[^\s]{1,512}(?:\?|/)(?:[^\s]{0,64})(?:token|secret|key)=", re.I),
    ),
)


def mark_untrusted_instructions(text: str) -> tuple[SafetyMarker, ...]:
    bounded = text[:100_000]
    return tuple(marker for marker, pattern in _RULES if pattern.search(bounded) is not None)
