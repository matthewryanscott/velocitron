"""The generator: `.petrinet` leaf net -> Python module (ADR 0058, Decision 1).

One module per leaf net, deterministic, no timestamp, stable text emitted
directly (no external formatter), so `--check` diffs stay clean and golden
files are byte-stable.

The two pipelines are joined by name: `lower_petrinet_text` gives the
Contribution IR (one span per statement, arc ids, arc handles),
`compile_petrinet_text` + `parse_net` give the `Net`. Every docstring's line
numbers come from the IR spans; the quoted lines come from the source text
itself. The carry rule and the `data cel` scope are the ones `play
check` and the Engine use: SC303 over the consumed tokens grouped by color,
and `engine.evaluate_produce_cel` over `{binding: place-keyed data}`.

References: ADR 0058 (Decisions 1, 2, 5); card `05-codegen-single-net.md`.

The generated module text still imports ``velocitron_netbase`` and
``velocitron_replay``. ``VelocitronNet`` lives in ``velocitron_netbase``
and replay lives in ``velocitron_replay``. Generated modules import
those packages directly. This module does not import ``velocitron``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from keyword import iskeyword
from typing import Any, Final, cast

from velocitron_engine import Arc, Net, Transition

from .hash import net_sha256

__all__ = ["CodegenError", "GeneratedModule", "generate_module"]

_NON_WORD: Final = re.compile(r"[^A-Za-z0-9]+")


class CodegenError(Exception):
    """Every generation failure collected, one per line, with `file:line`."""

    def __init__(self, messages: Sequence[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = tuple(messages)


@dataclass(frozen=True)
class GeneratedModule:
    """One generated net module: its text, and the facts tests count."""

    text: str
    net_name: str
    source: str
    sha256: str
    abstract_methods: tuple[str, ...]
    generated_handlers: tuple[str, ...]
    no_code_transitions: tuple[str, ...]
    actor: str | None
    guard_methods: dict[str, str]
    predicate_methods: dict[str, str]
    input_places: dict[str, tuple[str, ...]]
    output_places: dict[str, tuple[str, ...]]


def _camel(*parts: str) -> str:
    """`switch.owner` -> `SwitchOwner`; `net-name` -> `NetName`."""
    out: list[str] = []
    for part in parts:
        for chunk in _NON_WORD.split(str(part)):
            if chunk:
                out.append(chunk[0].upper() + chunk[1:])
    return "".join(out)


def _method_suffix(name: str) -> str:
    """A legal method-name suffix, or ``""`` (a failure)."""
    if not name.isidentifier() or iskeyword(name):
        return ""
    return name


def _span_lines(contribution: Mapping[str, Any]) -> tuple[int, int]:
    span = contribution["span"]
    return int(span["start"]["line"]), int(span["end"]["line"])


def _mapping(value: Any) -> Mapping[str, Any]:
    """The value as a string-keyed mapping, or an empty one."""
    if isinstance(value, Mapping):
        return cast(Mapping[str, Any], value)
    return {}


def _net_actor(net: Net) -> str | None:
    value = (net.annotations or {}).get("actor")
    return value if isinstance(value, str) else None


def _transition_actor(net: Net, transition: Transition) -> str | None:
    """The transition's `actor` fact, else the net's `net actor` default."""
    value = (transition.annotations or {}).get("actor")
    if isinstance(value, str):
        return value
    return _net_actor(net)


def _kept_for_actor(net: Net, transition: Transition, actor: str | None) -> bool:
    if actor is None:
        return True
    owner = _transition_actor(net, transition)
    return owner is None or owner == actor


def _class_name(net_name: str) -> str:
    name = _camel(net_name)
    if name.endswith("Net"):
        return name
    return name + "Net"


def _typeddict_name(transition: str) -> str:
    return _camel(transition) + "Outputs"


class _IRView:
    """The Contribution IR of one document, oriented for the generator.

    What the `Net` cannot say: per-transition line mentions (a statement
    mentions a transition when it targets one or declares an arc that
    joins it), the line of every arc by (place, transition, mode), and the
    `net` header line.
    """

    def __init__(self, contributions: Sequence[Mapping[str, Any]]) -> None:
        self.lines: dict[str, set[int]] = {}
        self.arc_line: dict[tuple[str, str, str], int] = {}
        self.header_line = 1
        for contribution in contributions:
            kind = str(contribution["kind"])
            start, end = _span_lines(contribution)
            target = _mapping(contribution.get("target"))
            if kind == "document.net-header" and str(target.get("type")) == "document":
                self.header_line = start
                continue
            if str(target.get("type")) == "transition":
                self.lines.setdefault(str(target["name"]), set()).update(
                    range(start, end + 1)
                )
                continue
            if str(target.get("type")) != "arc":
                continue
            value = _mapping(contribution["value"])
            transition_name: str | None = None
            place_name: str | None = None
            for endpoint in ("from", "to"):
                node = _mapping(value.get(endpoint))
                if str(node.get("type")) == "transition" and transition_name is None:
                    transition_name = str(node["name"])
                if str(node.get("type")) == "place" and place_name is None:
                    place_name = str(node["name"])
            if transition_name is not None:
                self.lines.setdefault(transition_name, set()).update(
                    range(start, end + 1)
                )
            if kind == "arc.declare" and transition_name and place_name:
                mode = str(value.get("mode", "produce"))
                self.arc_line[(place_name, transition_name, mode)] = start

    def line_ranges(self, name: str) -> str:
        lines = sorted(self.lines.get(name, ()))
        if not lines:
            return ""
        parts: list[str] = []
        run_start = previous = lines[0]
        for line in lines[1:]:
            if line == previous + 1:
                previous = line
                continue
            parts.append(_span_join(run_start, previous))
            run_start = previous = line
        parts.append(_span_join(run_start, previous))
        return ", ".join(parts)


def _span_join(start: int, end: int) -> str:
    return str(start) if start == end else f"{start}-{end}"


def _quote_source(ranges_text: str, text_lines: Sequence[str]) -> list[str]:
    """The verbatim source lines of one `a-b, c` range list."""
    out: list[str] = []
    for part in ranges_text.split(", ") if ranges_text else []:
        if "-" in part:
            first, last = part.split("-")
        else:
            first = last = part
        for number in range(int(first), int(last) + 1):
            if 1 <= number <= len(text_lines):
                out.append(text_lines[number - 1])
    return out


def _docstring(method_first_line: str, quoted: Sequence[str], indent: str) -> list[str]:
    out = [f'{indent}"""{method_first_line}']
    if quoted:
        out.append("")
        for line in quoted:
            out.append(f"{indent}    {line}".rstrip())
    out.append(f'{indent}"""')
    return out


def generate_module(
    net: Net,
    *,
    source: str,
    source_name: str,
    text: str,
    contributions: Sequence[Mapping[str, Any]],
    actor: str | None = None,
    is_async: bool = False,
) -> GeneratedModule:
    """Generate one net module.

    `net` is the parsed model; `text` the `.petrinet` source; `source_name`
    the name the spans carry; `source` the path as the user gave it
    (`SOURCE`). Collects every failure first and raises one
    :class:`CodegenError` naming them all, so the caller writes nothing on
    a failing net.
    """
    errors: list[str] = []
    view = _IRView(contributions)
    source_ = source.replace("\\", "/")
    text_lines = text.splitlines()
    sha = net_sha256(net)

    # ── the actor filter (ADR 0058, Decision 2) ─────────────────────
    kept: list[Transition] = []
    dropped: list[Transition] = []
    for transition in net.transitions:
        if _kept_for_actor(net, transition, actor):
            kept.append(transition)
        else:
            dropped.append(transition)

    # ── the input/output arcs per kept transition ───────────────────
    kept_names = {t.name for t in kept}
    inputs: dict[str, list[Arc]] = {}
    produces: dict[str, list[Arc]] = {}
    for arc in net.arcs:
        if arc.consume is not None and arc.to_transition in kept_names:
            inputs.setdefault(str(arc.to_transition), []).append(arc)
        if arc.produce is not None and arc.from_transition in kept_names:
            produces.setdefault(str(arc.from_transition), []).append(arc)

    # ── parameters: the consume and read places, arc order ──────────
    parameters: dict[str, list[str]] = {}
    for transition in kept:
        places: list[str] = []
        for arc in inputs.get(transition.name, ()):
            consume = arc.consume
            assert consume is not None
            if consume.mode == "inhibit":
                continue  # an inhibitor binds nothing, so no parameter
            if arc.from_place not in places:
                places.append(str(arc.from_place))
        parameters[transition.name] = places
        for place in places:
            if not place.isidentifier() or iskeyword(place):
                line = view.arc_line.get((place, transition.name, "consume"), 1)
                errors.append(
                    f"{source_name}:{line}: place ({place}) is a Python "
                    "keyword and cannot be a parameter; rename it"
                )

    # ── shared handler refs: one ref, one transition ────────────────
    ref_owners: dict[str, list[Transition]] = {}
    for transition in kept:
        if transition.handler is not None:
            ref_owners.setdefault(transition.handler, []).append(transition)
    for ref, owners in ref_owners.items():
        if len(owners) > 1:
            quoted = ", ".join(
                f"{source_name}:{min(view.lines.get(o.name, {1}))}" for o in owners
            )
            errors.append(
                f'handler ref "{ref}" is shared by '
                + " and ".join(f"[{o.name}]" for o in owners)
                + f" ({quoted})"
            )

    # ── the classification (after the actor filter) ─────────────────
    abstract = [t for t in kept if t.handler is not None]
    generated = [t for t in kept if t.handler is None]

    # ── guard and predicate methods ─────────────────────────────────
    guard_methods: dict[str, str] = {}
    for transition in kept:
        if transition.guard is not None:
            guard_methods[transition.guard] = f"guard_{transition.name}"
    predicate_methods: dict[str, str] = {}
    for transition in kept:
        for arc in inputs.get(transition.name, ()):
            consume = arc.consume
            assert consume is not None
            if consume.predicate is None or consume.predicate.handler is None:
                continue
            ref = consume.predicate.handler
            suffix = _method_suffix(ref)
            if not suffix:
                line = view.arc_line.get(
                    (str(arc.from_place), transition.name, str(consume.mode)), 1
                )
                errors.append(
                    f'predicate ref "{ref}" at {source_name}:{line} is not a '
                    "valid method name"
                )
                continue
            predicate_methods[ref] = f"predicate_{suffix}"

    # ── Literal aliases per `domain color.field` fact ───────────────
    domains = net.domains or {}
    alias_names = {key: _camel(key) for key in domains}

    # ── the generated bodies: every output filled ───────────────────
    body_lines: dict[str, list[str]] = {}
    for transition in generated:
        lines: list[str] = []
        for arc in produces.get(transition.name, ()):
            if arc.produce is None:  # unreachable: produces holds produce arcs
                continue
            template = arc.produce
            line = view.arc_line.get(
                (template.destination, transition.name, "produce"), 1
            )
            if template.data is not None:
                lines.append(
                    f"            {template.destination!r}: "
                    f"[Token(type={template.type!r}, "
                    f"data=deepcopy({_data_repr(template.data)}))],"
                )
            elif template.cel is not None:
                binding_items = ", ".join(
                    f"{place!r}: {place}" for place in parameters[transition.name]
                )
                lines.append(
                    f"            {template.destination!r}: [Token("
                    f"type={template.type!r}, "
                    f"data=self._cel({template.cel!r}, {{{binding_items}}}))],"
                )
            else:
                # The carry rule (SC303): exactly one consumed token of the
                # output's color; read tokens never carry.
                candidates = [
                    consume_arc
                    for consume_arc in inputs.get(transition.name, ())
                    if consume_arc.consume is not None
                    and consume_arc.consume.mode == "consume"
                    and consume_arc.consume.type == template.type
                ]
                if not candidates:
                    errors.append(
                        f"no rule fills [{transition.name}] "
                        f"-{template.type}-> ({template.destination}) at "
                        f"{source_name}:{line}: add a data cel or a handler fact"
                    )
                    continue
                if len(candidates) > 1:
                    errors.append(
                        f"the carry rule for [{transition.name}] "
                        f"-{template.type}-> ({template.destination}) at "
                        f"{source_name}:{line} finds {len(candidates)} consumed "
                        f"{template.type} tokens; it needs exactly one"
                    )
                    continue
                consume_arc = candidates[0]
                consume = consume_arc.consume
                assert consume is not None
                if consume.weight > 1:
                    errors.append(
                        f"the carry rule for [{transition.name}] "
                        f"-{template.type}-> ({template.destination}) at "
                        f"{source_name}:{line} found a weight of {consume.weight}; "
                        "it needs a weight of 1"
                    )
                    continue
                place = str(consume_arc.from_place)
                lines.append(
                    f"            {template.destination!r}: [self._carry("
                    f"{place}, {template.type!r}, {template.destination!r})],"
                )
        body_lines[transition.name] = lines

    if errors:
        raise CodegenError(errors)

    input_places = {t.name: tuple(parameters.get(t.name, ())) for t in kept}
    output_places: dict[str, tuple[str, ...]] = {}
    for t in kept:
        for a in produces.get(t.name, ()):
            if a.produce is None:
                continue
            output_places.setdefault(t.name, ())
            output_places[t.name] = (*output_places[t.name], str(a.produce.destination))

    text_out = _emit(
        net=net,
        view=view,
        source=source_,
        actor=actor,
        is_async=is_async,
        kept=kept,
        dropped=dropped,
        abstract=abstract,
        generated=generated,
        parameters=parameters,
        inputs=inputs,
        produces=produces,
        body_lines=body_lines,
        guard_methods=guard_methods,
        predicate_methods=predicate_methods,
        alias_names=alias_names,
        domains=domains,
        sha=sha,
        text_lines=text_lines,
        input_places=input_places,
        output_places=output_places,
    )
    return GeneratedModule(
        text=text_out,
        net_name=net.name,
        source=source_,
        sha256=sha,
        abstract_methods=tuple(t.name for t in abstract),
        generated_handlers=tuple(t.name for t in generated),
        no_code_transitions=tuple(t.name for t in dropped),
        actor=actor,
        guard_methods=guard_methods,
        predicate_methods=predicate_methods,
        input_places=input_places,
        output_places=output_places,
    )


def _data_repr(data: Any) -> str:
    """The repr of a parsed literal `data`: deterministic for the parsed value."""
    return repr(data)


def _emit(
    *,
    net: Net,
    view: _IRView,
    source: str,
    actor: str | None,
    is_async: bool,
    kept: Sequence[Transition],
    dropped: Sequence[Transition],
    abstract: Sequence[Transition],
    generated: Sequence[Transition],
    parameters: Mapping[str, Sequence[str]],
    inputs: Mapping[str, Sequence[Arc]],
    produces: Mapping[str, Sequence[Arc]],
    body_lines: Mapping[str, Sequence[str]],
    guard_methods: Mapping[str, str],
    predicate_methods: Mapping[str, str],
    alias_names: Mapping[str, str],
    domains: Mapping[str, Sequence[Any]],
    sha: str,
    text_lines: Sequence[str],
    input_places: Mapping[str, tuple[str, ...]],
    output_places: Mapping[str, tuple[str, ...]],
) -> str:
    out: list[str] = []
    out.append(f"# Generated by `velocitron codegen` from {source}. Do not edit.")
    # No `from __future__ import annotations` here: with postponed
    # annotations, TypedDict's runtime detection of `NotRequired` reads the
    # real objects (PEP 655) and would make every key Required.
    out.append("import abc")
    # The imports follow the module's use, so basedpyright reports no
    # unused-import error on a deterministic module: `deepcopy` copies a
    # literal `data`; `Literal` matches a `domain` fact; `NotRequired`
    # matches a `data`/`data cel` output; `TypedDict` matches a coded
    # transition; `Token` is always referenced by the annotations.
    uses_deepcopy = any(
        "deepcopy(" in line for lines in body_lines.values() for line in lines
    )
    uses_not_required = any(
        template.data is not None or template.cel is not None
        for arcs in produces.values()
        for arc in arcs
        if (template := arc.produce) is not None
    )
    uses_typeddict = any(output_places.values())
    typing_names: list[str] = []
    if alias_names:
        typing_names.append("Literal")
    if uses_not_required:
        typing_names.append("NotRequired")
    if uses_typeddict:
        typing_names.append("TypedDict")
    if typing_names:
        out.append("from typing import " + ", ".join(sorted(typing_names)))
    if uses_deepcopy:
        out.append("from copy import deepcopy")
    out.append("")
    out.append("from velocitron_netbase import VelocitronNet")
    out.append("from velocitron_engine import Token")
    if is_async:
        out.append("from velocitron_runtime import RuntimeContext")
    out.append("from velocitron_replay import ReplayBase")
    out.append("")
    if alias_names:
        out.append(
            "# One Literal alias per `domain color.field` fact, for the subclass"
        )
        out.append("# author; Token keeps dict data, the signatures do not use them.")
        for key in domains:
            values = ", ".join(repr(value) for value in domains[key])
            out.append(f"{alias_names[key]} = Literal[{values}]")
        out.append("")

    # ── one TypedDict per transition with code ──────────────────────
    coded = [t for t in kept if output_places[t.name]]
    for t in coded:
        out.append(f"class {_typeddict_name(t.name)}(TypedDict):")
        for arc in produces[t.name]:
            template = arc.produce
            assert template is not None
            line = view.arc_line.get((template.destination, t.name, "produce"), 1)
            comment = f"  # {source}:{line}"
            not_required = template.data is not None or template.cel is not None
            if not_required:
                out.append(
                    f"    {template.destination}: NotRequired[list[Token]]{comment}"
                )
            else:
                out.append(f"    {template.destination}: list[Token]{comment}")
        out.append("")
    if coded:
        out.append("")
        out.append("")

    # ── the class ───────────────────────────────────────────────────
    out.append(f"class {_class_name(net.name)}(VelocitronNet, abc.ABC):")
    header = text_lines[view.header_line - 1].rstrip()
    class_doc: list[str] = [header, f"{source}:{view.header_line}"]
    if dropped:
        class_doc.append("Not this actor: " + ", ".join(f"[{t.name}]" for t in dropped))
    out.append(f'    """{class_doc[0]}')
    for line in class_doc[1:]:
        out.append(f"    {line}")
    out.append('    """')
    out.append(f"    NET_NAME = {net.name!r}")
    out.append(f"    SOURCE = {source!r}")
    out.append(f"    SOURCE_SHA256 = {sha!r}")
    out.append(f"    ASYNC = {is_async!r}")
    out.append(f"    ACTOR = {actor!r}")

    def table(name: str, items: Mapping[str, Any]) -> None:
        out.append(f"    {name} = {{")
        for key, value in items.items():
            out.append(f"        {key!r}: {value!r},")
        out.append("    }")

    handler_refs = {t.handler or "": f"fire_{t.name}" for t in abstract}
    table("HANDLER_REFS", handler_refs)
    table("GUARD_REFS", dict(guard_methods))
    table("PREDICATE_REFS", dict(predicate_methods))
    generated_methods = {t.name: f"fire_{t.name}" for t in generated}
    table("GENERATED_METHODS", generated_methods)
    table(
        "INPUT_PLACES",
        {name: places for name, places in input_places.items() if places},
    )
    table(
        "OUTPUT_PLACES",
        {name: places for name, places in output_places.items() if places},
    )
    out.append("")

    def parameter_list(t: Transition) -> str:
        return "".join(f", {place}: list[Token]" for place in parameters[t.name])

    def method_docstring(t: Transition) -> list[str]:
        ranges = view.line_ranges(t.name)
        first = f"[{t.name}]: {source}:{ranges}"
        quoted = _quote_source(ranges, text_lines)
        return _docstring(first, quoted, "        ")

    for t in abstract:
        out.append("    @abc.abstractmethod")
        if is_async:
            out.append(
                f"    async def fire_{t.name}(self{parameter_list(t)}, "
                f"*, context: RuntimeContext) -> {_typeddict_name(t.name)}:"
            )
        else:
            out.append(
                f"    def fire_{t.name}(self{parameter_list(t)}) -> "
                f"{_typeddict_name(t.name)}:"
            )
        out.extend(method_docstring(t))
        out.append("")
    for t in generated:
        if is_async:
            out.append(
                f"    async def fire_{t.name}(self{parameter_list(t)}, "
                f"*, context: RuntimeContext) -> {_typeddict_name(t.name)}:"
            )
        else:
            out.append(
                f"    def fire_{t.name}(self{parameter_list(t)}) -> "
                f"{_typeddict_name(t.name)}:"
            )
        out.extend(method_docstring(t))
        out.append("        return {")
        out.extend(body_lines[t.name])
        out.append("        }")
        out.append("")
    for ref, method_name in guard_methods.items():
        owner = _guard_owner(kept, ref)
        out.append("    @abc.abstractmethod")
        out.append(f"    def {method_name}(self{parameter_list(owner)}) -> bool:")
        out.extend(method_docstring(owner))
        out.append("")
    for ref, method_name in predicate_methods.items():
        owner = _predicate_owner(kept, ref, inputs)
        out.append("    @abc.abstractmethod")
        out.append(f"    def {method_name}(self, token: Token) -> bool:")
        ranges = view.line_ranges(owner.name)
        first = f"predicate {ref!r}: {source}:{ranges}"
        out.extend(_docstring(first, _quote_source(ranges, text_lines), "        "))
        out.append("")

    # ── the replay class (ADR 0058, Decision 7) ─────────────────────
    # `Replay<Net>(ReplayBase, <Net>Net)`: the mixin first in the MRO —
    # it overrides the adapter seams so no method ever runs — and the
    # net class's own declarative tables, signatures, and generated
    # handlers (unused). The stubs (one per abstract method) make the
    # class concrete; replay never calls them.
    out.append(
        f"class Replay{_class_name(net.name)}(ReplayBase, {_class_name(net.name)}):"
    )
    out.append(f'    """The replay class for {net.name}: answers every handler call')
    out.append("    from the cursor.")
    out.append("")
    out.append("    Stubs make it concrete; replay never calls them.")
    out.append('    """')
    out.append("")
    for t in abstract:
        if is_async:
            out.append(
                f"    async def fire_{t.name}(self{parameter_list(t)}, "
                f"*, context: RuntimeContext) -> {_typeddict_name(t.name)}:"
            )
        else:
            out.append(
                f"    def fire_{t.name}(self{parameter_list(t)}) -> "
                f"{_typeddict_name(t.name)}:"
            )
        out.append(f'        raise AssertionError("replay never calls fire_{t.name}")')
        out.append("")
    for ref, method_name in guard_methods.items():
        owner = _guard_owner(kept, ref)
        out.append(f"    def {method_name}(self{parameter_list(owner)}) -> bool:")
        out.append('        raise AssertionError("replay never calls guard")')
        out.append("")
    for ref, method_name in predicate_methods.items():
        out.append(f"    def {method_name}(self, token: Token) -> bool:")
        out.append('        raise AssertionError("replay never calls predicate")')
        out.append("")
    return "\n".join(out) + "\n"


def _guard_owner(kept: Sequence[Transition], ref: str) -> Transition:
    """The transition whose guard names `ref`."""
    for t in kept:
        if t.guard == ref:
            return t
    raise KeyError(ref)


def _predicate_owner(
    kept: Sequence[Transition],
    ref: str,
    inputs: Mapping[str, Sequence[Arc]],
) -> Transition:
    """The kept transition with an input arc whose predicate handler is `ref`."""
    for t in kept:
        for arc in inputs.get(t.name, ()):
            consume = arc.consume
            if (
                consume is not None
                and consume.predicate is not None
                and consume.predicate.handler == ref
            ):
                return t
    raise KeyError(ref)
