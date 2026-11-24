"""Map-key equality for the Rust CEL backend.

``common-expression-language`` 0.10.0 (cel-rust 0.14.5) compares scalar
``int``, ``uint``, and ``double`` on one number line, so ``1 == 1.0`` is
true, and list elements and map values use that equality. Map keys stay
type-tagged. In the crate, ``{1: 'a'} == {1u: 'a'}`` is false, ``1u`` does
not find the key ``1``, and a ``double`` is rejected as a key:
``{1: 'a'}[1.0]`` and ``1.0 in {1: 'a'}`` fail instead of selecting ``'a'``.
The interpreter special-cases ``==``, ``!=``, ``in``, and indexing before
overload lookup, so a registered function cannot replace the operators.

This module still rewrites those four operators. ``==`` and ``!=`` hand the
values back to the crate. A ``uint`` arrives in Python as an ``int`` (Python
has one integer type), so the crate then sees one key type and its own
scalar equality, which matches the conformance rows, including a map whose
keys were ``int`` and ``uint``. ``in`` and indexing do the same, except when
the key is a ``double``: the helper compares that double with the stored
keys the way the CEL conformance ``*_lossy_double`` cases do, and a missing
double key is false for ``in`` rather than an error. A bool is not a
number. Arithmetic is not rewritten, so ``1 + 1.0`` still has no overload.
"""

from __future__ import annotations

import math
from typing import Any, cast

_EQ = "__velocitron_eq"
_NE = "__velocitron_ne"
_IN = "__velocitron_in"
_IDX = "__velocitron_idx"

_programs: dict[str, Any] = {}


class _ParseError(Exception):
    """The expression is not in the subset this rewriter parses."""


class _Parser:
    """Rewrite ``==``, ``!=``, ``in``, and indexing; emit the rest unchanged."""

    def __init__(self, source: str) -> None:
        self._source = source
        self._tokens = _lex(source)
        self._at = 0

    def parse(self) -> str:
        rewritten = self._expr()
        if not self._check("EOF"):
            raise _ParseError(self._source)
        return rewritten

    def _expr(self) -> str:
        condition = self._or()
        if not self._eat("?"):
            return condition
        yes = self._or()
        if not self._eat(":"):
            raise _ParseError(self._source)
        no = self._expr()
        return f"({condition} ? {yes} : {no})"

    def _or(self) -> str:
        left = self._and()
        while self._eat("||"):
            left = f"({left} || {self._and()})"
        return left

    def _and(self) -> str:
        left = self._rel()
        while self._eat("&&"):
            left = f"({left} && {self._rel()})"
        return left

    def _rel(self) -> str:
        left = self._add()
        while self._peek() in {"==", "!=", "<", "<=", ">", ">=", "in"}:
            op = self._peek()
            self._at += 1
            right = self._add()
            if op == "==":
                left = f"{_EQ}({left}, {right})"
            elif op == "!=":
                left = f"{_NE}({left}, {right})"
            elif op == "in":
                left = f"{_IN}({left}, {right})"
            else:
                left = f"({left} {op} {right})"
        return left

    def _add(self) -> str:
        left = self._mul()
        while self._peek() in {"+", "-"}:
            op = self._tokens[self._at][0]
            self._at += 1
            left = f"({left} {op} {self._mul()})"
        return left

    def _mul(self) -> str:
        left = self._unary()
        while self._peek() in {"*", "/", "%"}:
            op = self._tokens[self._at][0]
            self._at += 1
            left = f"({left} {op} {self._unary()})"
        return left

    def _unary(self) -> str:
        if self._eat("!"):
            return f"(!{self._unary()})"
        if self._eat("-"):
            return f"(-{self._unary()})"
        return self._member()

    def _member(self) -> str:
        term = self._primary()
        while True:
            if self._eat("."):
                name = self._take("IDENT")
                if self._eat("("):
                    args = self._args()
                    term = f"{term}.{name}({args})"
                else:
                    term = f"{term}.{name}"
            elif self._eat("["):
                index = self._expr()
                if not self._eat("]"):
                    raise _ParseError(self._source)
                term = f"{_IDX}({term}, {index})"
            elif self._eat("{"):
                fields = self._fields()
                term = f"{term}{{{fields}}}"
            else:
                return term

    def _primary(self) -> str:
        kind = self._peek()
        if kind in {"NUM", "STR", "IDENT"}:
            text = self._tokens[self._at][1]
            self._at += 1
            if kind == "IDENT" and self._eat("("):
                return f"{text}({self._args()})"
            return text
        if self._eat("("):
            inner = self._expr()
            if not self._eat(")"):
                raise _ParseError(self._source)
            return f"({inner})"
        if self._eat("["):
            return f"[{self._exprs(']')}]"
        if self._eat("{"):
            return f"{{{self._map()}}}"
        raise _ParseError(self._source)

    def _args(self) -> str:
        return self._exprs(")")

    def _exprs(self, closer: str) -> str:
        if self._eat(closer):
            return ""
        items = [self._expr()]
        while self._eat(","):
            if self._check(closer):
                break
            items.append(self._expr())
        if not self._eat(closer):
            raise _ParseError(self._source)
        return ", ".join(items)

    def _map(self) -> str:
        if self._eat("}"):
            return ""
        items: list[str] = []
        while True:
            key = self._expr()
            if not self._eat(":"):
                raise _ParseError(self._source)
            items.append(f"{key}: {self._expr()}")
            if self._eat("}"):
                return ", ".join(items)
            if not self._eat(","):
                raise _ParseError(self._source)
            if self._eat("}"):
                return ", ".join(items)

    def _fields(self) -> str:
        if self._eat("}"):
            return ""
        items: list[str] = []
        while True:
            name = self._take("IDENT")
            if not self._eat(":"):
                raise _ParseError(self._source)
            items.append(f"{name}: {self._expr()}")
            if self._eat("}"):
                return ", ".join(items)
            if not self._eat(","):
                raise _ParseError(self._source)
            if self._eat("}"):
                return ", ".join(items)

    def _peek(self) -> str:
        return self._tokens[self._at][0]

    def _check(self, kind: str) -> bool:
        return self._peek() == kind

    def _eat(self, kind: str) -> bool:
        if self._peek() != kind:
            return False
        self._at += 1
        return True

    def _take(self, kind: str) -> str:
        if self._peek() != kind:
            raise _ParseError(self._source)
        text = self._tokens[self._at][1]
        self._at += 1
        return text


def rewrite(source: str) -> str:
    """Return ``source`` with numeric-key operators routed to the helpers.

    An expression this parser does not recognize is returned unchanged, so
    the backend still reports its own syntax error.
    """
    try:
        return _Parser(source).parse()
    except _ParseError:
        return source


def evaluation_context(data: dict[str, Any]) -> Any:
    """A CEL context with ``data`` plus the numeric-key helpers."""
    import cel  # pyright: ignore[reportMissingImports]

    variables = {key: value for key, value in data.items() if not callable(value)}
    functions = {key: value for key, value in data.items() if callable(value)}
    functions.update(
        {
            _EQ: _eq,
            _NE: _ne,
            _IN: _contains,
            _IDX: _index,
        }
    )
    return cel.Context(variables=variables, functions=functions)  # pyright: ignore[reportUnknownMemberType]


def _native(op: str) -> Any:
    program = _programs.get(op)
    if program is None:
        import cel  # pyright: ignore[reportMissingImports]

        source = {
            "==": "___a == ___b",
            "!=": "___a != ___b",
            "in": "___a in ___b",
            "[]": "___a[___b]",
        }[op]
        program = cel.compile(source)  # pyright: ignore[reportUnknownMemberType]
        _programs[op] = program
    return program


def _delegate(op: str, left: Any, right: Any) -> Any:
    try:
        return _native(op).execute({"___a": left, "___b": right})  # pyright: ignore[reportUnknownMemberType]
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _is_number(value: object) -> bool:
    """An ``int`` or ``double``. A bool is not a number."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _int_double_order(number: int, double: float) -> int | None:
    """``-1`` / ``0`` / ``1``, or ``None`` when ``double`` is NaN.

    Same rule as CEL conformance and cel-cpp: convert the integer to double
    once the double lies in the integer type's range. A Python ``int`` above
    ``2**63 - 1`` is a ``uint``; nothing else survives the trip out of the
    crate as a wider integer.
    """
    if math.isnan(double):
        return None
    if number > 2**63 - 1:
        if double > float(2**64 - 1):
            return -1
        if double < 0:
            return 1
    else:
        if double > float(2**63 - 1):
            return -1
        if double < -float(2**63):
            return 1
    as_double = float(number)
    if as_double < double:
        return -1
    if as_double > double:
        return 1
    return 0


def _numbers_equal(left: int | float, right: int | float) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) or math.isnan(right):
            return False
        return left == right
    if isinstance(left, float):
        order = _int_double_order(int(right), left)
    elif isinstance(right, float):
        order = _int_double_order(left, right)
    else:
        return left == right
    return order == 0


def _mapping(value: Any) -> dict[Any, Any] | None:
    if isinstance(value, dict):
        return cast("dict[Any, Any]", value)
    return None


def _eq(left: Any, right: Any) -> bool:
    # 0.10.0's scalar equality, after a uint has become a Python int.
    return bool(_delegate("==", left, right))


def _ne(left: Any, right: Any) -> bool:
    return bool(_delegate("!=", left, right))


def _double_key(needle: Any, mapping: dict[Any, Any]) -> tuple[bool, Any]:
    """``(True, value)`` when a stored key matches ``needle``.

    The crate rejects a double as a map key. ``needle`` is compared with
    each stored key by the conformance lossy-double rule. The value may
    itself be null, so a miss is a separate flag.
    """
    for stored, value in mapping.items():
        if _is_number(stored) and _numbers_equal(needle, stored):
            return True, value
    return False, None


def _contains(needle: Any, haystack: Any) -> bool:
    mapping = _mapping(haystack)
    # A double needle must not reach the crate: ``1.0 in {1: 'a'}`` is true
    # and ``2.0 in {1: 'a'}`` is false, not a type error.
    if mapping is not None and isinstance(needle, float):
        return _double_key(needle, mapping)[0]
    return bool(_delegate("in", needle, haystack))


def _index(container: Any, key: Any) -> Any:
    mapping = _mapping(container)
    if mapping is not None and isinstance(key, float):
        found, value = _double_key(key, mapping)
        if not found:
            raise RuntimeError(f"no such key: {key}")
        return value
    return _delegate("[]", container, key)


def _lex(source: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    i = 0
    n = len(source)
    while i < n:
        ch = source[i]
        if ch.isspace():
            i += 1
            continue
        if ch in "'\"" or _string_prefix(source, i) is not None:
            text, i = _string(source, i)
            tokens.append(("STR", text))
            continue
        if ch == "." and i + 1 < n and source[i + 1].isdigit():
            text, i = _number(source, i)
            tokens.append(("NUM", text))
            continue
        if ch.isdigit():
            text, i = _number(source, i)
            tokens.append(("NUM", text))
            continue
        if ch == "_" or ch.isalpha():
            start = i
            i += 1
            while i < n and (source[i] == "_" or source[i].isalnum()):
                i += 1
            text = source[start:i]
            tokens.append(("in" if text == "in" else "IDENT", text))
            continue
        two = source[i : i + 2]
        if two in {"==", "!=", "<=", ">=", "&&", "||"}:
            tokens.append((two, two))
            i += 2
            continue
        tokens.append((ch, ch))
        i += 1
    tokens.append(("EOF", ""))
    return tokens


def _string_prefix(source: str, i: int) -> str | None:
    """A ``b``/``r`` string prefix at ``i``, or ``None`` when this is an ident."""
    rest = source[i:]
    for prefix in ("br", "bR", "Br", "BR", "b", "B", "r", "R"):
        if (
            rest.startswith(prefix)
            and len(rest) > len(prefix)
            and rest[len(prefix)] in "'\""
        ):
            return prefix
    return None


def _string(source: str, i: int) -> tuple[str, int]:
    prefix = _string_prefix(source, i) or ""
    start = i
    i += len(prefix)
    quote = source[i]
    triple = source[i : i + 3] == quote * 3
    raw = "r" in prefix.lower()
    if triple:
        i += 3
        closer = quote * 3
        while i < len(source) and not source.startswith(closer, i):
            i += 2 if not raw and source[i] == "\\" else 1
        if not source.startswith(closer, i):
            raise _ParseError(source)
        i += 3
    else:
        i += 1
        while i < len(source) and source[i] != quote:
            i += 2 if not raw and source[i] == "\\" else 1
        if i >= len(source):
            raise _ParseError(source)
        i += 1
    return source[start:i], i


def _number(source: str, i: int) -> tuple[str, int]:
    start = i
    if source[i] == "0" and i + 1 < len(source) and source[i + 1] in "xX":
        i += 2
        while i < len(source) and source[i] in "0123456789abcdefABCDEF":
            i += 1
        if i < len(source) and source[i] in "uU":
            i += 1
        return source[start:i], i
    if source[i] == ".":
        i += 1
        while i < len(source) and source[i].isdigit():
            i += 1
        i = _exponent(source, i)
        return source[start:i], i
    while i < len(source) and source[i].isdigit():
        i += 1
    if (
        i < len(source)
        and source[i] == "."
        and i + 1 < len(source)
        and source[i + 1].isdigit()
    ):
        i += 1
        while i < len(source) and source[i].isdigit():
            i += 1
        i = _exponent(source, i)
        return source[start:i], i
    if i < len(source) and source[i] in "eE":
        i = _exponent(source, i)
        return source[start:i], i
    if i < len(source) and source[i] in "uU":
        i += 1
    return source[start:i], i


def _exponent(source: str, i: int) -> int:
    if i >= len(source) or source[i] not in "eE":
        return i
    j = i + 1
    if j < len(source) and source[j] in "+-":
        j += 1
    if j >= len(source) or not source[j].isdigit():
        return i
    j += 1
    while j < len(source) and source[j].isdigit():
        j += 1
    return j
