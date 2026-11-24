"""RFC 8785 JSON for rendered token labels.

This module is the source of truth for that encoding. ``velocitron_petrinet``
imports ``render_canonical_json`` from here. This module does not import
``velocitron``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any, cast

def _json_string(value: str) -> str:
    """Render one Unicode-scalar JSON string without ASCII escaping."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as error:
        raise ValueError("JSON strings must contain only Unicode scalars") from error
    return json.dumps(value, ensure_ascii=False)


def _binary64(value: float) -> str:
    """Render a finite binary64 using the RFC 8785/ECMAScript thresholds."""
    if not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    if value == 0:
        return "0"

    negative = value < 0
    rendered = repr(-value if negative else value).lower()
    coefficient, separator, raw_exponent = rendered.partition("e")
    integer, _, fraction = coefficient.partition(".")
    significand = (integer + fraction).lstrip("0")
    exponent = (int(raw_exponent) if separator else 0) - len(fraction)

    digits = significand.rstrip("0")
    exponent += len(significand) - len(digits)
    adjusted = exponent + len(digits) - 1

    if -6 <= adjusted < 21:
        decimal_at = len(digits) + exponent
        if decimal_at <= 0:
            magnitude = "0." + ("0" * -decimal_at) + digits
        elif decimal_at >= len(digits):
            magnitude = digits + ("0" * (decimal_at - len(digits)))
        else:
            magnitude = digits[:decimal_at] + "." + digits[decimal_at:]
    else:
        magnitude = digits[0]
        if len(digits) > 1:
            magnitude += "." + digits[1:]
        magnitude += "e" + str(adjusted)
    return ("-" if negative else "") + magnitude


def render_canonical_json(value: Any, *, indent: int | None = None) -> str:
    """Render JSON with one RFC 8785 primitive representation.

    Arrays retain semantic order. Object members use RFC 8785's UTF-16 sort
    order; indentation changes whitespace only, never primitive spellings.
    """
    if indent is not None and indent < 0:
        raise ValueError("indent must be nonnegative")

    def render(item: Any, level: int) -> str:
        if item is None:
            return "null"
        if item is True:
            return "true"
        if item is False:
            return "false"
        if isinstance(item, int):
            if abs(item) > 9_007_199_254_740_991:
                raise ValueError("JSON integer exceeds the safe IEEE-754 range")
            return str(item)
        if isinstance(item, float):
            return _binary64(item)
        if isinstance(item, str):
            return _json_string(item)
        if isinstance(item, list):
            values = [render(child, level + 1) for child in cast(list[Any], item)]
            if not values:
                return "[]"
            if indent is None:
                return "[" + ",".join(values) + "]"
            padding = " " * (indent * (level + 1))
            closing = " " * (indent * level)
            return (
                "[\n" + padding + (",\n" + padding).join(values) + "\n" + closing + "]"
            )
        if isinstance(item, Mapping):
            raw_object = cast(Mapping[Any, Any], item)
            if not all(isinstance(key, str) for key in raw_object):
                raise TypeError("JSON object keys must be strings")
            object_value = cast(Mapping[str, Any], raw_object)
            try:
                keys = sorted(object_value, key=lambda key: key.encode("utf-16be"))
            except UnicodeEncodeError as error:
                raise ValueError(
                    "JSON object keys must contain only Unicode scalars"
                ) from error
            members = [
                _json_string(key)
                + (":" if indent is None else ": ")
                + render(object_value[key], level + 1)
                for key in keys
            ]
            if not members:
                return "{}"
            if indent is None:
                return "{" + ",".join(members) + "}"
            padding = " " * (indent * (level + 1))
            closing = " " * (indent * level)
            return (
                "{\n" + padding + (",\n" + padding).join(members) + "\n" + closing + "}"
            )
        raise TypeError(f"not a JSON value: {type(item).__name__}")

    return render(value, 0)


