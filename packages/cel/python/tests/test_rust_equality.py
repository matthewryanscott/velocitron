"""The Rust adapter's numeric-key rewrite, without executing the backend."""

from __future__ import annotations

from velocitron_cel._rust_equality import rewrite


def test_rewrite_routes_equality_membership_and_index() -> None:
    # given: expressions whose operators the Rust crate special-cases
    # when: they are rewritten
    # then: equality, inequality, membership, and index call the helpers,
    # and the call preserves field selection after an index
    assert rewrite("1 == 1.0") == "__velocitron_eq(1, 1.0)"
    assert rewrite("1 != 1.0") == "__velocitron_ne(1, 1.0)"
    assert rewrite("1.0 in {1: 'a'}") == "__velocitron_in(1.0, {1: 'a'})"
    assert rewrite("{1: 'a'}[1u]") == "__velocitron_idx({1: 'a'}, 1u)"
    assert (
        rewrite("token.key == binding.requests[0].key")
        == "__velocitron_eq(token.key, __velocitron_idx(binding.requests, 0).key)"
    )


def test_rewrite_leaves_strings_arithmetic_and_ordering() -> None:
    # given: an equality sign inside a string, mixed arithmetic, and ordering
    # when: the expression is rewritten
    # then: the string is untouched, addition stays an operator, and ordering
    # stays an operator so the crate's comparer still runs
    assert rewrite("'==' == '=='") == "__velocitron_eq('==', '==')"
    assert rewrite("1 + 1.0") == "(1 + 1.0)"
    assert rewrite("clock.now >= deadline") == "(clock.now >= deadline)"
    assert rewrite("false && (1/0 == 1)") == "(false && (__velocitron_eq((1 / 0), 1)))"


def test_rewrite_returns_unrecognized_syntax_unchanged() -> None:
    # given: a token sequence this parser does not accept
    # when: it is rewritten
    # then: the original text is kept, so the backend reports the syntax error
    assert rewrite("5. == 5.0") == "5. == 5.0"
    assert rewrite(">") == ">"
