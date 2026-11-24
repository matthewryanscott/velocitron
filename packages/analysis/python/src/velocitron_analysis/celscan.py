"""Read the shape of a net's CEL: which token fields it tests, and how.

The prover derives finite data domains from the literals and comparisons
that a net's CEL states (``branch == 'main'``, ``token.isbn ==
binding.waiting[0].isbn``, ``clock.now >= hold.remindAt``). This
module turns one CEL expression into a small tree and lists its comparisons
over references. It never evaluates CEL; the engine does that.

velocitron bundles celpy, whose parser is pure Python, so this works whatever
backend evaluates the net. An expression celpy cannot parse yields an opaque
node, and the prover reports the facts that depend on it as unknown.

The portable compile/eval adapter lives in ``velocitron_cel``. This scanner
stays here: it reads celpy's parse tree and does not evaluate CEL.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from velocitron_cel import load_celpy

_parser: Any = None

# A reference is a root name and a path of field names and list indexes:
# `binding.waiting[0].isbn` is ("binding", ("waiting", 0, "isbn")).
Path = tuple[str | int, ...]


@dataclass(frozen=True)
class Ref:
    root: str
    path: Path


@dataclass(frozen=True)
class Lit:
    value: Any


@dataclass(frozen=True)
class Cmp:
    op: str  # "==", "!=", "<", "<=", ">", ">=", "in"
    left: Node
    right: Node


@dataclass(frozen=True)
class Call:
    name: str
    args: tuple[Node, ...]


@dataclass(frozen=True)
class Seq:
    """A node whose children are tested or combined as booleans: !, &&, ||,
    ?:, or a list literal."""

    kind: str  # "not" | "and" | "or" | "cond" | "list"
    items: tuple[Node, ...]


@dataclass(frozen=True)
class MapLit:
    entries: tuple[tuple[Node, Node], ...]


@dataclass(frozen=True)
class Opaque:
    """A shape this scanner does not read (arithmetic, macros, a method call).

    ``terms`` reads a sum of references and number literals, such as
    ``since + idleFor`` or ``now - since``: each term with its sign. It is
    empty for any other shape."""

    text: str
    refs: tuple[Ref, ...]
    terms: tuple[tuple[int, Ref | Lit], ...] = ()


Node = Ref | Lit | Cmp | Call | Seq | MapLit | Opaque

_CONVERSIONS = frozenset({"double", "int", "uint"})

_RELATIONS = {
    "relation_eq": "==",
    "relation_ne": "!=",
    "relation_lt": "<",
    "relation_le": "<=",
    "relation_gt": ">",
    "relation_ge": ">=",
    "relation_in": "in",
}


def parse(expression: str) -> Node:
    """The small tree of one CEL expression, or :class:`Opaque` when celpy
    cannot parse it."""
    global _parser
    if _parser is None:
        _parser = load_celpy().celparser.CELParser()
    try:
        tree: Any = _parser.parse(expression)
    except Exception:  # noqa: BLE001 - an unparsable expression is opaque
        return Opaque(expression, ())
    return _node(tree)


def _children(tree: Any) -> list[Any]:
    return list(tree.children)


def _is_tree(item: Any) -> bool:
    return hasattr(item, "data")


def _node(tree: Any) -> Node:
    # celpy wraps every level of precedence in a one-child node.
    while (
        _is_tree(tree)
        and len(tree.children) == 1
        and tree.data
        in (
            "expr",
            "conditionalor",
            "conditionaland",
            "relation",
            "addition",
            "multiplication",
            "unary",
            "member",
            "primary",
        )
    ):
        tree = tree.children[0]
    if not _is_tree(tree):
        return Opaque(str(tree), ())
    data = tree.data
    children = _children(tree)
    if data == "expr" and len(children) == 3:
        return Seq("cond", tuple(_node(child) for child in children))
    if data == "conditionalor":
        return Seq("or", tuple(_node(child) for child in children))
    if data == "conditionaland":
        return Seq("and", tuple(_node(child) for child in children))
    if data == "relation" and len(children) == 2:
        relation = children[0]
        op = _RELATIONS.get(relation.data)
        if op is not None and len(relation.children) == 1:
            return Cmp(op, _node(relation.children[0]), _node(children[1]))
    if data == "unary" and len(children) == 2 and _is_tree(children[0]):
        if children[0].data == "unary_not":
            return Seq("not", (_node(children[1]),))
    if data == "literal":
        return _literal(children[0])
    if data in ("ident", "member_dot", "member_index"):
        ref = _ref(tree)
        if ref is not None:
            return ref
    if data == "paren_expr" and len(children) == 1:
        return _node(children[0])
    if data == "ident_arg" and len(children) == 2:
        name = str(children[0])
        args = tuple(_node(expr) for expr in _children(children[1]))
        if name in _CONVERSIONS and len(args) == 1:
            # A numeric conversion keeps the order of its argument.
            return args[0]
        return Call(name, args)
    if data == "ident_arg" and len(children) == 1:
        return Call(str(children[0]), ())
    if data == "list_lit":
        items = _children(children[0]) if children else []
        return Seq("list", tuple(_node(item) for item in items))
    if data == "map_lit":
        if not children:
            return MapLit(())
        flat = [_node(item) for item in _children(children[0])]
        pairs = tuple(zip(flat[0::2], flat[1::2], strict=True))
        return MapLit(pairs)
    if data == "addition":
        terms = _sum(tree)
        if terms is not None:
            return Opaque(data, tuple(_refs_in(tree)), terms)
    return Opaque(data, tuple(_refs_in(tree)))


def _sum(tree: Any) -> tuple[tuple[int, Ref | Lit], ...] | None:
    """The signed terms of an addition of references and number literals,
    or ``None`` when some operand is anything else."""
    children = _children(tree)
    if (
        len(children) == 2
        and _is_tree(children[0])
        and children[0].data in ("addition_add", "addition_sub")
        and len(children[0].children) == 1
    ):
        head = _sum(children[0].children[0])
        tail = _as_term(_node(children[1]))
        if head is None or tail is None:
            return None
        sign = 1 if children[0].data == "addition_add" else -1
        return (*head, (sign, tail))
    term = _as_term(_node(tree))
    return ((1, term),) if term is not None else None


def _as_term(node: Node) -> Ref | Lit | None:
    """A reference or a number literal, the only operands a sum keeps."""
    if isinstance(node, Ref):
        return node
    if (
        isinstance(node, Lit)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return node
    return None


def _literal(token: Any) -> Node:
    kind = getattr(token, "type", "")
    text = str(token)
    try:
        if kind == "STRING_LIT":
            return Lit(_string(text))
        if kind == "BOOL_LIT":
            return Lit(text == "true")
        if kind == "NULL_LIT":
            return Lit(None)
        if kind == "INT_LIT":
            return Lit(int(text, 0))
        if kind == "UINT_LIT":
            return Lit(int(text.rstrip("uU"), 0))
        if kind == "FLOAT_LIT":
            return Lit(float(text))
    except ValueError:
        pass
    return Opaque(text, ())


def _string(text: str) -> str:
    raw = text.startswith(("r", "R"))
    body = text[1:] if raw else text
    quote = body[:3] if body[:3] in ('"""', "'''") else body[0]
    inner = body[len(quote) : -len(quote)]
    if raw:
        return inner
    return inner.encode("latin-1", "backslashreplace").decode("unicode_escape")


def _ref(tree: Any) -> Ref | None:
    path: list[str | int] = []
    while True:
        data = tree.data
        children = _children(tree)
        if data == "ident":
            path.reverse()
            return Ref(str(children[0]), tuple(path))
        if data == "member_dot":
            path.append(str(children[1]))
            tree = _unwrap(children[0])
        elif data == "member_index":
            index = _node(children[1])
            if not isinstance(index, Lit) or not isinstance(index.value, int):
                return None
            path.append(index.value)
            tree = _unwrap(children[0])
        else:
            return None
        if not _is_tree(tree):
            return None


def _unwrap(tree: Any) -> Any:
    while (
        _is_tree(tree)
        and len(tree.children) == 1
        and tree.data
        in (
            "member",
            "primary",
        )
    ):
        tree = tree.children[0]
    return tree


def _refs_in(tree: Any) -> list[Ref]:
    """Every reference inside a tree the scanner does not read.

    A reference inside a longer one (``clock`` in ``clock.now``) is dropped.
    """
    found: list[Ref] = []
    for node in tree.iter_subtrees_topdown():
        if node.data in ("ident", "member_dot", "member_index"):
            ref = _ref(node)
            if ref is not None:
                found.append(ref)
    return [
        ref
        for ref in found
        if not any(
            other.root == ref.root
            and len(other.path) > len(ref.path)
            and other.path[: len(ref.path)] == ref.path
            for other in found
        )
    ]


def walk(node: Node) -> Iterator[Node]:
    """Every node of a tree, parents first."""
    yield node
    if isinstance(node, Cmp):
        yield from walk(node.left)
        yield from walk(node.right)
    elif isinstance(node, Call):
        for arg in node.args:
            yield from walk(arg)
    elif isinstance(node, Seq):
        for item in node.items:
            yield from walk(item)
    elif isinstance(node, MapLit):
        for key, value in node.entries:
            yield from walk(key)
            yield from walk(value)


def refs(node: Node) -> Iterator[Ref]:
    """Every reference in a tree, including those inside opaque parts."""
    for item in walk(node):
        if isinstance(item, Ref):
            yield item
        elif isinstance(item, Opaque):
            yield from item.refs


def boolean_refs(node: Node) -> Iterator[Ref]:
    """References used directly as booleans: ``connected``, ``!x``, ``a && b``."""
    if isinstance(node, Ref):
        yield node
    elif isinstance(node, Seq) and node.kind in ("not", "and", "or"):
        for item in node.items:
            yield from boolean_refs(item)
    elif isinstance(node, Seq) and node.kind == "cond":
        yield from boolean_refs(node.items[0])


def negated(node: Node, flip: bool = False) -> Iterator[Cmp]:
    """Comparisons a value can pass by being false: under an odd number of
    ``!``, or the condition of ``?:`` (its else branch takes it false)."""
    if isinstance(node, Cmp):
        if flip:
            yield node
    elif isinstance(node, Seq) and node.kind == "not":
        yield from negated(node.items[0], not flip)
    elif isinstance(node, Seq) and node.kind in ("and", "or"):
        for item in node.items:
            yield from negated(item, flip)
    elif isinstance(node, Seq) and node.kind == "cond":
        yield from negated(node.items[0], True)
        for item in node.items[1:]:
            yield from negated(item, flip)
