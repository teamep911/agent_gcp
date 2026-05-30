"""
Monitor_v2 — Data Masker
Mask thông tin nhạy cảm trước khi persist vào DB hoặc gửi ra ngoài (Telegram/Chat).
"""

import os
import re
from copy import deepcopy
from typing import Any

MASK_ENABLED = os.getenv("MASK_ENABLED", "true").lower() == "true"
MASK_REPLACEMENT = os.getenv("MASK_REPLACEMENT", "[REDACTED]")

# Patterns nhạy cảm cần mask
_SENSITIVE_PATTERNS = [
    # Password trong connection string
    (re.compile(r"(password\s*=\s*)([^\s;\"']+)", re.IGNORECASE), r"\1" + MASK_REPLACEMENT),
    # Oracle connection string dạng user/pass@host
    (re.compile(r"([a-zA-Z0-9_]+)/([^@\s]+)@"), r"\1/" + MASK_REPLACEMENT + "@"),
    # JDBC URL với password
    (re.compile(r"(jdbc:[^;]+password=)([^;\"'\s]+)", re.IGNORECASE), r"\1" + MASK_REPLACEMENT),
    # Internal IP addresses — tuỳ chọn, uncomment nếu cần
    # (re.compile(r"\b(10\.\d{1,3}\.\d{1,3}\.\d{1,3})\b"), MASK_REPLACEMENT),
    # (re.compile(r"\b(192\.168\.\d{1,3}\.\d{1,3})\b"), MASK_REPLACEMENT),
]

# Keys trong dict cần mask value
_SENSITIVE_KEYS = {
    "password", "passwd", "secret", "token", "credential",
    "api_key", "private_key", "oem_password",
}


def mask_string(text: str) -> str:
    """Mask một chuỗi text."""
    if not MASK_ENABLED or not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def mask_payload(obj: Any) -> Any:
    """
    Đệ quy mask dict/list/string.
    Dùng trước khi persist vào DB hoặc gửi ra Telegram.
    """
    if not MASK_ENABLED:
        return obj

    if isinstance(obj, dict):
        masked = {}
        for k, v in obj.items():
            if k.lower() in _SENSITIVE_KEYS:
                masked[k] = MASK_REPLACEMENT
            else:
                masked[k] = mask_payload(v)
        return masked

    if isinstance(obj, list):
        return [mask_payload(item) for item in obj]

    if isinstance(obj, str):
        return mask_string(obj)

    return obj
