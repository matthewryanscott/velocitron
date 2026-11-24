"""Source-tree tests for the CEL compile/eval adapter."""

from __future__ import annotations

import importlib.util

import pytest

from velocitron_cel import (
    CelAdapter,
    CelEvalError,
    CelExprAdapter,
    CelRustAdapter,
    CelpyAdapter,
    get_default_adapter,
)


def test_celpy_adapter_evaluates_a_predicate_and_nested_fields() -> None:
    # given: the bundled celpy backend
    adapter = CelpyAdapter()
    # when: a comparison and a nested field selection are compiled and evaluated
    above = adapter.eval(adapter.compile("n >= 1"), {"n": 1})
    below = adapter.eval(adapter.compile("n >= 1"), {"n": 0})
    nested = adapter.eval(adapter.compile("a.b == 1"), {"a": {"b": 1}})
    total = adapter.eval(adapter.compile("n + 1"), {"n": 1})
    # then: results are native Python values, including bool identity
    assert isinstance(adapter, CelAdapter)
    assert above is True
    assert below is False
    assert nested is True
    assert total == 2


def test_celpy_adapter_evaluates_mixed_map_and_list_literals() -> None:
    # given: a map and a list that mix literals with a bound value
    adapter = CelpyAdapter()
    context = {"binding": {"pending": [{"id": "d-1"}]}}
    # when: both expressions are evaluated
    mapped = adapter.eval(
        adapter.compile(
            "{'kind': 'held', 'delivery': binding.pending[0].id, 'attempt': 1}"
        ),
        context,
    )
    listed = adapter.eval(
        adapter.compile("[1, 'a', binding.pending[0].id]"),
        context,
    )
    # then: the structures are plain Python containers
    assert mapped == {"kind": "held", "delivery": "d-1", "attempt": 1}
    assert listed == [1, "a", "d-1"]


def test_celpy_adapter_compiles_a_free_variable_and_rejects_syntax() -> None:
    # given: the bundled backend
    adapter = CelpyAdapter()
    # when: a free variable is compiled, and a broken expression is compiled
    compiled = adapter.compile("priority > 5")
    # then: syntax is checked now, and the broken expression raises
    assert compiled is not None
    with pytest.raises(Exception):
        adapter.compile("> > >")


def test_celpy_adapter_raises_cel_eval_error_on_evaluation_failure() -> None:
    # given: expressions that fail while evaluating
    adapter = CelpyAdapter()
    missing = adapter.compile("missing.field")
    divided = adapter.compile("1 / 0")
    # when: each is evaluated
    # then: both failures are CelEvalError
    with pytest.raises(CelEvalError):
        adapter.eval(missing, {})
    with pytest.raises(CelEvalError):
        adapter.eval(divided, {})


def test_numeric_kinds_compare_on_one_number_line() -> None:
    # given: the bundled backend. The CEL spec orders int, uint, and double
    # across those types, and treats equal numbers as equal. Arithmetic does
    # not mix them. A NaN is not equal to a number and cannot be ordered.
    adapter = CelpyAdapter()

    def evaluate(expr: str) -> object:
        return adapter.eval(adapter.compile(expr), {})

    # when: mixed comparisons, mixed arithmetic, and a NaN are evaluated
    # then: ordering and equality follow the number line
    assert evaluate("1 >= 1.0") is True
    assert evaluate("1 < 1.0") is False
    assert evaluate("120 >= 120.0") is True
    assert evaluate("240 >= 360.0") is False
    assert evaluate("1 == 1.0") is True
    assert evaluate("1 != 1.0") is False
    assert evaluate("1u == 1") is True
    assert evaluate("1.0 >= 1") is True
    assert evaluate("double('NaN') == 1") is False
    assert evaluate("-0.0 == 0") is True
    assert evaluate("-1 == 1u") is False
    # Conformance compares past 2**53 by converting the integer to double.
    assert evaluate("9007199254740993 == 9007199254740992.0") is True
    assert evaluate("9223372036854775807 == 9223372036854775808.0") is True
    assert evaluate("9223372036854775807 < 9223372036854775808.0") is False
    assert evaluate("{1: 'a'}[1.0]") == "a"
    assert evaluate("1.0 in {1: 'a'}") is True
    assert evaluate("{1: 'a'} == {1u: 'a'}") is True
    with pytest.raises(CelEvalError):
        evaluate("1 + 1.0")
    with pytest.raises(CelEvalError):
        evaluate("double('NaN') >= 1")
    with pytest.raises(CelEvalError):
        evaluate("1 == 'a'")


def test_matches_runs_on_the_bundled_backend() -> None:
    # given: a CEL matches call
    adapter = CelpyAdapter()
    # when: it is evaluated with no activation
    matched = adapter.eval(adapter.compile("'hello'.matches('h.*')"), {})
    # then: the bundled backend, with re2 or the stand-in, accepts it
    assert matched is True


def test_get_default_adapter_is_celpy_when_rust_is_absent() -> None:
    # given: a process where the Rust backend is not installed. The C++
    # binding may be installed; auto-detection does not select it (ADR 0066).
    if importlib.util.find_spec("cel") is not None:
        pytest.skip("common-expression-language is installed")
    # when: the default adapter is selected
    adapter = get_default_adapter()
    # then: it is the bundled celpy adapter and not an engine helper
    assert type(adapter) is CelpyAdapter
    assert not hasattr(adapter, "slow_backend_hint")


def test_optional_adapters_import_their_backends_only_when_called() -> None:
    # given: the optional adapters, constructed with no backend import yet
    cpp = CelExprAdapter()
    rust = CelRustAdapter()
    # when: each is asked to compile only if its extra is absent
    # then: construction succeeded, and a missing extra raises ImportError
    assert isinstance(cpp, CelAdapter)
    assert isinstance(rust, CelAdapter)
    if importlib.util.find_spec("cel_expr_python") is None:
        with pytest.raises(ImportError):
            cpp.compile("1")
    if importlib.util.find_spec("cel") is None:
        with pytest.raises(ImportError):
            rust.compile("1")


def test_package_exports_the_cache_and_the_cli_hint() -> None:
    # given: the package module
    import velocitron_cel

    # then: the result cache and the CLI hint live in this package
    assert callable(velocitron_cel.CachingCelAdapter)
    assert callable(velocitron_cel.slow_backend_hint)
