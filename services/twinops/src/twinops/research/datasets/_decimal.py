"""Shared ASCII-decimal parsing for preparation and dataset adapters."""

from __future__ import annotations

import math
import re


_ASCII_DECIMAL = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$", re.ASCII
)


def parse_ascii_decimal(token: object, *, context: str) -> float:
    """Parse one finite ASCII-decimal token without Python-only extensions."""

    if not isinstance(token, str):
        raise ValueError(f"{context}: numeric token must be an ASCII decimal string")
    normalized = token.strip(" \t")
    if _ASCII_DECIMAL.fullmatch(normalized) is None:
        raise ValueError(f"{context}: numeric token must use ASCII decimal syntax")
    try:
        value = float(normalized)
    except (OverflowError, ValueError) as error:
        raise ValueError(
            f"{context}: numeric token is not representable as a float"
        ) from error
    if not math.isfinite(value):
        raise ValueError(f"{context}: numeric token must be finite")
    return value
