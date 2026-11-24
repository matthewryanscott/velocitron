"""Behavior that changed when the Rust CEL backend moved to 0.10.0.

``common-expression-language`` 0.7 through 0.9 (cel-rust 0.14) changed five
things. None of them appear in an in-repo net, skill, doc example, or
conformance case: no CEL expression calls ``contains`` on a list, map, or
bytes value, calls ``min`` or ``max``, uses a reserved word as an identifier,
or calls ``int`` or ``uint``. The prover reads ``double()``, ``int()``, and
``uint()`` as their argument and does not evaluate them (``proofs.md``).
``type(token.owner) == string`` is parsed by lint and is not evaluated by a
net. These tests pin the new Rust results, and the rows every backend
already shares.
"""

from __future__ import annotations

import pytest
from _cel_adapters import ADAPTER_IDS, adapters, cel_rust_available

from velocitron_cel import CelAdapter, CelEvalError, CelRustAdapter

# cel-rust 0.14.4 rejects these as identifiers. A name that only contains
# one (``var_2``) and a string map key (``{"var": 1}``) are still legal.
_RESERVED = (
    "as",
    "break",
    "const",
    "continue",
    "else",
    "for",
    "function",
    "if",
    "import",
    "let",
    "loop",
    "package",
    "namespace",
    "return",
    "var",
    "void",
    "while",
)


def _eval(
    adapter: CelAdapter, expr: str, data: dict[str, object] | None = None
) -> object:
    return adapter.eval(adapter.compile(expr), {} if data is None else data)


@pytest.mark.parametrize("adapter", adapters(), ids=ADAPTER_IDS)
def test_contains_is_a_string_function(adapter: CelAdapter) -> None:
    # given: a string contains call, which stayed in the core function set
    # when: it is evaluated
    matched = _eval(adapter, "'abc'.contains('b')")
    missed = _eval(adapter, "'abc'.contains('z')")
    # then: the string is searched, on every backend
    assert matched is True
    assert missed is False


@pytest.mark.skipif(
    not cel_rust_available(), reason="common-expression-language is not installed"
)
@pytest.mark.parametrize(
    "expr",
    ["[1, 2].contains(1)", "{'a': 1}.contains('a')", "b'abc'.contains(b'b')"],
)
def test_rust_contains_is_not_defined_on_containers(expr: str) -> None:
    # given: contains on a list, a map, or bytes. 0.10.0 keeps contains for
    # strings only; the crate no longer resolves it on a container.
    adapter = CelRustAdapter()
    # when: the call is evaluated
    # then: it is an unknown function, not a membership test
    with pytest.raises(CelEvalError):
        _eval(adapter, expr)


@pytest.mark.skipif(
    not cel_rust_available(), reason="common-expression-language is not installed"
)
@pytest.mark.parametrize(
    "expr",
    ["min(1, 2)", "max(1, 2)", "min([1, 2])", "[1, 2].min()", "[1, 2].max()"],
)
def test_rust_min_and_max_are_not_in_the_core(expr: str) -> None:
    # given: min and max, which 0.14 moved out of the core function set
    adapter = CelRustAdapter()
    # when: each call form is evaluated
    # then: the core does not provide them
    with pytest.raises(CelEvalError):
        _eval(adapter, expr)


@pytest.mark.skipif(
    not cel_rust_available(), reason="common-expression-language is not installed"
)
@pytest.mark.parametrize("word", _RESERVED)
def test_rust_rejects_a_reserved_word_as_an_identifier(word: str) -> None:
    # given: a reserved word used as a variable
    adapter = CelRustAdapter()
    # when: it is compiled
    # then: the parser rejects it. A name that merely contains the word, and
    # the same text as a string map key, still compile and evaluate.
    with pytest.raises(ValueError):
        adapter.compile(f"{word} == 1")
    assert adapter.compile(f"{word}_2 == 1") is not None
    assert _eval(adapter, f"{{'{word}': 1}}['{word}']") == 1


@pytest.mark.parametrize("adapter", adapters(), ids=ADAPTER_IDS)
def test_type_comparisons_name_the_spec_types(adapter: CelAdapter) -> None:
    # given: type tests, including the form lint accepts
    # (``type(token.owner) == string``)
    # when: each is evaluated
    # then: the comparison is true on every backend. 0.10.0's native type()
    # reports uint and null under those spec names.
    assert _eval(adapter, "type(1) == int") is True
    assert _eval(adapter, "type(1u) == uint") is True
    assert _eval(adapter, "type(1.0) == double") is True
    assert _eval(adapter, "type('a') == string") is True
    assert _eval(adapter, "type(null) == null_type") is True
    assert _eval(adapter, "type(true) == bool") is True
    assert (
        _eval(adapter, "type(token.owner) == string", {"token": {"owner": "ada"}})
        is True
    )


@pytest.mark.skipif(
    not cel_rust_available(), reason="common-expression-language is not installed"
)
def test_rust_type_returns_the_spec_name() -> None:
    # given: the native type() 0.10.0 returns to Python as a name
    adapter = CelRustAdapter()
    # when: the types that used to come back under a different name are read
    # then: uint is "uint" and null is "null_type"
    assert _eval(adapter, "type(1)") == "int"
    assert _eval(adapter, "type(1u)") == "uint"
    assert _eval(adapter, "type(1.0)") == "double"
    assert _eval(adapter, "type('a')") == "string"
    assert _eval(adapter, "type(null)") == "null_type"
    assert _eval(adapter, "type(true)") == "bool"


@pytest.mark.parametrize("adapter", adapters(), ids=ADAPTER_IDS)
def test_int_and_uint_convert_in_range_and_reject_overflow(adapter: CelAdapter) -> None:
    # given: conversions inside the target type, and conversions that do not
    # fit. 0.10.0 raises on overflow instead of wrapping or saturating.
    # when: each is evaluated
    # then: an in-range value converts, and an overflow is an eval error
    assert _eval(adapter, "int(1.9)") == 1
    assert _eval(adapter, "int(-1.9)") == -1
    assert _eval(adapter, "uint(1.9)") == 1
    assert _eval(adapter, "int(1u)") == 1
    assert _eval(adapter, "uint(1)") == 1
    for expr in (
        "int(9223372036854775808u)",
        "uint(-1)",
        "int(1e300)",
        "int(double('NaN'))",
        "uint(double('NaN'))",
    ):
        with pytest.raises(CelEvalError):
            _eval(adapter, expr)


@pytest.mark.parametrize("adapter", adapters(), ids=ADAPTER_IDS)
def test_a_double_key_finds_an_int_entry_including_a_null_value(
    adapter: CelAdapter,
) -> None:
    # given: map lookup by a double, the case 0.10.0 still rejects on its own
    # when: the key is a double, including -0.0 selecting a null value
    found = _eval(adapter, "{1: 'a'}[1.0]")
    null = _eval(adapter, "{0: null}[-0.0]")
    member = _eval(adapter, "0.0 in {0: null}")
    # then: the entry is selected, and a null value is null rather than a miss
    assert found == "a"
    assert null is None
    assert member is True


@pytest.mark.skipif(
    not cel_rust_available(), reason="common-expression-language is not installed"
)
def test_rust_map_lookup_uses_the_lossy_double_rule() -> None:
    # given: an int key past 2**53 and the double it converts to. The crate
    # rejects the double as a key; the helper applies the conformance rule.
    adapter = CelRustAdapter()
    # when: the map is indexed by that double
    found = _eval(adapter, "{9007199254740993: 'a'}[9007199254740992.0]")
    # then: the entry is the one the lossy comparison selects
    assert found == "a"
