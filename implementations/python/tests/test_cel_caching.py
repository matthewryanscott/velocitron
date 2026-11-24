"""CachingCelAdapter keeps results per expression and activation values."""

from __future__ import annotations

from typing import Any

import pytest

from velocitron_cel import (
    CachingCelAdapter,
    CelAdapter,
    CelEvalError,
    get_default_adapter,
)


class Counting(CelAdapter):
    def __init__(self) -> None:
        self.inner = get_default_adapter()
        self.evals = 0

    def compile(self, expr: str) -> Any:
        return self.inner.compile(expr)

    def eval(self, compiled: Any, data: dict[str, Any]) -> Any:
        self.evals += 1
        return self.inner.eval(compiled, data)


def test_equal_values_are_evaluated_once():
    counting = Counting()
    adapter = CachingCelAdapter(counting)
    compiled = adapter.compile("token.n > 1")
    assert adapter.eval(compiled, {"token": {"n": 2}}) is True
    assert adapter.eval(compiled, {"token": {"n": 2}}) is True
    assert adapter.eval(compiled, {"token": {"n": 1}}) is False
    assert counting.evals == 2


def test_values_of_different_types_are_told_apart():
    counting = Counting()
    adapter = CachingCelAdapter(counting)
    compiled = adapter.compile("token.v")
    assert adapter.eval(compiled, {"token": {"v": True}}) is True
    one = adapter.eval(compiled, {"token": {"v": 1}})
    assert one == 1 and one is not True
    assert counting.evals == 2


def test_an_eval_error_is_raised_again_from_the_cache():
    counting = Counting()
    adapter = CachingCelAdapter(counting)
    compiled = adapter.compile("1 / token.n")
    for _ in range(2):
        with pytest.raises(CelEvalError):
            adapter.eval(compiled, {"token": {"n": 0}})
    assert counting.evals == 1


def test_a_container_result_is_a_new_copy_each_time():
    adapter = CachingCelAdapter(get_default_adapter())
    compiled = adapter.compile("{'a': [1, 2]}")
    first = adapter.eval(compiled, {})
    first["a"].append(3)
    assert adapter.eval(compiled, {}) == {"a": [1, 2]}


class Stub(CelAdapter):
    """Takes any value, which not every backend does."""

    def __init__(self) -> None:
        self.evals = 0

    def compile(self, expr: str) -> Any:
        return expr

    def eval(self, compiled: Any, data: dict[str, Any]) -> Any:
        self.evals += 1
        return True


def test_an_activation_that_is_not_json_is_evaluated_each_time():
    stub = Stub()
    adapter = CachingCelAdapter(stub)
    compiled = adapter.compile("true")
    for _ in range(2):
        assert adapter.eval(compiled, {"token": {"raw": b"x"}}) is True
    assert stub.evals == 2


def test_the_cache_is_cleared_at_its_limit():
    counting = Counting()
    adapter = CachingCelAdapter(counting, limit=2)
    compiled = adapter.compile("token.n")
    for n in (1, 2, 3, 1):
        adapter.eval(compiled, {"token": {"n": n}})
    assert counting.evals == 4
