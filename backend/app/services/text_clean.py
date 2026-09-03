"""Text cleaning rules — port of SolarSense worker TEXT_CLEAN.

Source reference:
  solarsense-worker/preprocess/multimodal_processors.py::_CLEAN_RULES / TextCleanProcessor
"""

from __future__ import annotations

import re
from typing import Any

# rule_id -> (description, list of (pattern, replacement))
CLEAN_RULES: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "ocr_coords": (
        "清洗 OCR 坐标/布局标签 (DeepSeek-OCR 输出)",
        [
            (r"<\|ref\|>.*?<\|/ref\|>\s*<\|det\|>.*?<\|/det\|>\s*\n?", ""),
            (r"<\|ref\|>.*?<\|/ref\|>", ""),
            (r"<\|det\|>.*?<\|/det\|>", ""),
        ],
    ),
    "extra_whitespace": (
        "合并多余空行/空格",
        [
            (r"[ \t]+$", ""),
            (r"\n{3,}", "\n\n"),
            (r"[ \t]{2,}", " "),
        ],
    ),
    "pii_mask": (
        "常见 PII mask (手机/身份证/邮箱)",
        [
            (r"\b(1[3-9]\d)\d{4}(\d{4})\b", r"\1****\2"),
            (r"\b(\d{6})\d{8}(\w{4})\b", r"\1********\2"),
            (r"\b([\w.-]+)@([\w.-]+)\b", r"***@\2"),
        ],
    ),
    "chinese_noise": (
        "中文 OCR 常见误识 (全角→半角)",
        [
            ("０", "0"),
            ("１", "1"),
            ("２", "2"),
            ("３", "3"),
            ("４", "4"),
            ("５", "5"),
            ("６", "6"),
            ("７", "7"),
            ("８", "8"),
            ("９", "9"),
            ("Ａ", "A"),
            ("Ｂ", "B"),
            ("Ｃ", "C"),
            ("Ｄ", "D"),
            ("　", " "),
        ],
    ),
}

DEFAULT_RULES = ["ocr_coords", "extra_whitespace", "chinese_noise"]


def clean_text(
    text: str,
    rules: list[str] | None = None,
    custom_regex: list[dict[str, Any]] | None = None,
) -> str:
    content = text or ""
    selected = rules if rules is not None else list(DEFAULT_RULES)
    for rule_id in selected:
        spec = CLEAN_RULES.get(rule_id)
        if not spec:
            continue
        _, patterns = spec
        for pattern, replacement in patterns:
            if len(pattern) == 1 and not pattern.startswith("\\") and "(" not in pattern:
                # plain char replace (chinese_noise fullwidth map)
                content = content.replace(pattern, replacement)
            else:
                flags = re.MULTILINE if pattern.endswith("$") else 0
                content = re.sub(pattern, replacement, content, flags=flags)

    for index, rule in enumerate(custom_regex or [], start=1):
        if not isinstance(rule, dict):
            raise ValueError(f"第 {index} 条自定义正则规则必须包含 pattern 和 replacement")
        pattern = rule.get("pattern")
        replacement = rule.get("replacement", "")
        if not isinstance(pattern, str) or not pattern.strip():
            raise ValueError(f"第 {index} 条自定义正则规则的 pattern 不能为空")
        if not isinstance(replacement, str):
            raise ValueError(f"第 {index} 条自定义正则规则的 replacement 必须是字符串")
        try:
            compiled = re.compile(pattern)
            compiled.sub(replacement, "")
        except (re.error, IndexError) as exc:
            raise ValueError(f"第 {index} 条自定义正则规则不符合 Python re 语法: {exc}") from exc
        content = compiled.sub(replacement, content)

    return content
