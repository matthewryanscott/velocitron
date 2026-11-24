"""Check a play: resolve it against its net, then play every path.

Resolution loads the net (or composes several), resolves every place,
transition, template, color and label, and reports ``SC2xx`` errors before
anything plays. Playback runs each step through the real :class:`Engine`:
an injection through ``inject_token(s)``, a firing through ``reserve`` and
``settle`` with outputs the play supplies (symbolic firing), so
enablement, binding, timers, read and inhibit arcs, correlates, guards and
deposit are the engine's own rules. A path stops at its first failing step
(``SC3xx``).

This module is the source of truth for that check. It does not import
``velocitron``. Journal durability stays in ``velocitron_journal``.
``records_to_play`` lives in this package. The checker does not call it.
The CLI ships in ``velocitron_cli``.

References: spec/play-language.md; ADR 0031.
"""

from __future__ import annotations

import difflib
import json
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from velocitron_cel import get_default_adapter
from velocitron_dsl import PetrinetDslError
from velocitron_engine import (
    DepositViolation,
    EnablementExplanation,
    Engine,
    FiringPolicyInput,
    FiringRecord,
    FiringReservation,
    HandlerError,
    HandlerRegistry,
    InjectionRecord,
    Marking,
    Net,
    PRIORITY_FIRING_POLICY,
    ProduceTemplate,
    Token,
    TransitionHandlerOutput,
    domain_violation,
    net_fills,
    produce_templates,
    symbolic_outputs,
)
from velocitron_merge import NetValidationError as MergeNetValidationError
from velocitron_merge import merge_composition, port_fusion_map
from velocitron_petrinet import (
    NetValidationError,
    compile_petrinet_text,
    parse_composition,
    parse_net,
    read_petrinet_text,
    validate_net,
)
from velocitron_play import (
    AdvanceBody,
    AssumeGuardBody,
    AssumePredicateBody,
    Condition,
    Diagnostic,
    FireBody,
    InjectBody,
    NameRef,
    Play,
    PlayError,
    PlayPath,
    Position,
    Step,
    TokenExpr,
    UpdateBody,
)
from velocitron_viz import Decoration, Decorations, read_decorations

from .kept_start import KeptStartError, build_start, kept_records
from .replay import markings_after_records

# ── The net a play plays against ────────────────────────────────────


@dataclass(frozen=True)
class PlayNet:
    """The resolved net: one net, or the merge of a composition.

    ``document`` is the net's canonical JSON for a single net (named
    markings, views), ``None`` for a composition. ``place_names`` maps every
    name a play may write to the net's place name: a composition's fused
    port answers to each member's qualified name. ``decorations`` are the
    net's own, carried over from each constituent for a composition.
    ``refined`` maps each transition a composition refines to the alias of
    its refining net.
    """

    net: Net
    label: str
    document: Mapping[str, Any] | None
    place_names: Mapping[str, str]
    decorations: Decorations
    composed: bool
    refined: Mapping[str, str] = field(default_factory=dict[str, str])


# ── Results ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CheckResult:
    """One ``expect`` condition: its text, whether it held, and the values."""

    text: str
    ok: bool
    detail: str = ""
    kind: str = ""

    def as_json(self) -> dict[str, Any]:
        return {"text": self.text, "ok": self.ok, "detail": self.detail}


OutputRule = Literal["net", "play", "merge", "carry", "nothing"]


@dataclass(frozen=True)
class OutputSource:
    """Which rule filled one produce template of a fired transition."""

    place: str
    color: str
    rule: OutputRule


@dataclass(frozen=True)
class StepResult:
    """One played step. ``index`` counts from 0 over the path's steps,
    inherited ones included; ``path`` names the path that declares it.

    For a firing, ``binding`` is the full binding and ``consumed`` / ``read``
    split it; ``produced`` is what the engine deposited. For an injection,
    ``produced`` holds the injected tokens and ``replaced`` what an update
    removed. An ``expect`` step changes nothing and carries its ``checks``.
    ``markings[i]`` is the net's marking after ``records[i]`` alone applied,
    with ``markings[-1]`` identical to ``after`` — one marking per record, so
    a reader sees the clock token the injection laid down before the firings
    the same advance matured.
    """

    step: Step
    path: str
    index: int
    before: Marking
    after: Marking
    records: tuple[FiringRecord | InjectionRecord, ...] = ()
    markings: tuple[Marking, ...] = ()
    binding: Mapping[str, Sequence[Token]] = field(
        default_factory=dict[str, Sequence[Token]]
    )
    consumed: Mapping[str, Sequence[Token]] = field(
        default_factory=dict[str, Sequence[Token]]
    )
    read: Mapping[str, Sequence[Token]] = field(
        default_factory=dict[str, Sequence[Token]]
    )
    produced: Mapping[str, Sequence[Token]] = field(
        default_factory=dict[str, Sequence[Token]]
    )
    replaced: Mapping[str, Sequence[Token]] = field(
        default_factory=dict[str, Sequence[Token]]
    )
    outputs: tuple[OutputSource, ...] = ()
    checks: tuple[CheckResult, ...] = ()


@dataclass(frozen=True)
class StepFailure:
    """The step a path stopped at, with its ``SC3xx`` diagnostic."""

    step: Step
    path: str
    index: int
    before: Marking
    diagnostic: Diagnostic
    checks: tuple[CheckResult, ...] = ()
    explanation: EnablementExplanation | None = None
    enabled: tuple[str, ...] = ()


@dataclass(frozen=True)
class PlayTrace:
    """One path's playback: the starting marking, every step played, and the
    failure that stopped it, if any. ``steps[i].after`` is
    ``steps[i + 1].before``. ``inherited`` counts the steps replayed from the
    path it branches from."""

    play: Play
    subject: PlayNet
    path: PlayPath
    initial: Marking
    steps: tuple[StepResult, ...]
    failure: StepFailure | None
    inherited: int

    @property
    def passed(self) -> bool:
        return self.failure is None

    @property
    def final(self) -> Marking:
        return self.steps[-1].after if self.steps else self.initial


@dataclass(frozen=True)
class PlayReport:
    """Every checked path of one play."""

    play: Play
    subject: PlayNet
    traces: tuple[PlayTrace, ...]

    @property
    def passed(self) -> bool:
        return all(trace.passed for trace in self.traces)

    def trace(self, path: str) -> PlayTrace | None:
        return next((t for t in self.traces if t.path.name == path), None)

    def diagnostics(self) -> list[Diagnostic]:
        """One diagnostic per distinct failing step. A failure inside an
        inherited prefix is reported once, under the path that declares the
        step, with the other paths it blocks."""
        failures: dict[tuple[str, int, int], list[PlayTrace]] = {}
        for trace in self.traces:
            if trace.failure is None:
                continue
            step = trace.failure.step
            key = (trace.failure.path, step.position.line, step.position.column)
            failures.setdefault(key, []).append(trace)
        diagnostics: list[Diagnostic] = []
        for (owner, _line, _column), traces in failures.items():
            failure = traces[0].failure
            assert failure is not None
            blocked = [t.path.name for t in traces if t.path.name != owner]
            details = list(failure.diagnostic.details)
            if blocked:
                details.append("blocked paths: " + ", ".join(blocked))
            diagnostics.append(
                Diagnostic(
                    failure.diagnostic.code,
                    failure.diagnostic.message,
                    failure.diagnostic.source,
                    failure.diagnostic.position,
                    tuple(details),
                )
            )
        return diagnostics


# ── Resolution ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _With:
    place: str
    describe: str
    subset: dict[str, Any] | None = None
    token: Token | None = None
    index: int | None = None


@dataclass(frozen=True)
class _Output:
    tokens: tuple[Token, ...] = ()
    merge: dict[str, Any] | None = None
    nothing: bool = False


@dataclass(frozen=True)
class _Fire:
    transition: str
    withs: tuple[_With, ...]
    outputs: Mapping[int, _Output]  # produce-template index → output


@dataclass(frozen=True)
class _Inject:
    place: str
    tokens: tuple[Token, ...]
    replace: bool


@dataclass(frozen=True)
class _Advance:
    place: str
    color: str
    seconds: int | float
    relative: bool


@dataclass(frozen=True)
class _Condition:
    source: Condition
    place: str | None = None
    tokens: tuple[Token, ...] = ()
    transitions: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Expect:
    conditions: tuple[_Condition, ...]


@dataclass(frozen=True)
class _Assume:
    """An ``assume`` step's resolution: which handler refs it answers, the
    value it gives them, and the step (via :class:`_PlannedStep`) that scopes
    them.

    A guard assumption is keyed by its transition; a predicate assumption
    applies to every consume arc whose predicate names the ref."""

    transition: str | None
    guard_ref: str | None
    predicate_ref: str | None
    value: bool


_Resolved = _Fire | _Inject | _Advance | _Expect | _Assume


class _Resolver:
    def __init__(self, play: Play, subject: PlayNet) -> None:
        self.play = play
        self.subject = subject
        self.net = subject.net
        self.places = {place.name: place for place in self.net.places}
        self.transitions = {tr.name: tr for tr in self.net.transitions}
        self.templates: dict[str, Token] = {}
        for name, literal in play.templates.items():
            assert literal.color is not None
            self.templates[name] = Token(literal.color, literal.data)

    def error(
        self, code: str, message: str, position: Position, details: Sequence[str] = ()
    ) -> PlayError:
        return PlayError(
            Diagnostic(code, message, self.play.source, position, tuple(details))
        )

    def place(self, ref: NameRef) -> str:
        resolved = self.subject.place_names.get(ref.name)
        if resolved is None:
            raise self.error(
                "SC202",
                f"the net has no place ({ref.name})",
                ref.position,
                _suggest(ref.name, self.subject.place_names),
            )
        return resolved

    def transition(self, ref: NameRef) -> str:
        if ref.name not in self.transitions:
            refining = self.subject.refined.get(ref.name)
            raise self.error(
                "SC203",
                f"the net has no transition [{ref.name}]",
                ref.position,
                [f"the composition refines [{ref.name}] by {refining}"]
                if refining is not None
                else _suggest(ref.name, self.transitions),
            )
        return ref.name

    def template(self, ref: NameRef) -> Token:
        token = self.templates.get(ref.name)
        if token is None:
            raise self.error(
                "SC204", f"no template ${ref.name} is defined", ref.position
            )
        return token

    def token_for(
        self, expr: TokenExpr, place: str, colors: Sequence[str] | None = None
    ) -> Token:
        """A token for ``place``: its color must be one the place accepts
        (or one of ``colors``, when given); a bare ``{json}`` needs exactly
        one candidate color."""
        candidates = list(colors) if colors is not None else self.places[place].accepts
        if isinstance(expr, NameRef):
            token = self.template(expr)
            position = expr.position
        else:
            position = expr.position
            if expr.color is None:
                if len(candidates) != 1:
                    raise self.error(
                        "SC207",
                        f"({place}) takes several colors "
                        f"({', '.join(candidates)}); write the color before the data",
                        position,
                    )
                token = Token(candidates[0], expr.data)
            else:
                token = Token(expr.color, expr.data)
        if token.type not in candidates:
            raise self.error(
                "SC207",
                f"({place}) does not take color {token.type} "
                f"(it takes {', '.join(candidates)})",
                position,
            )
        return token

    def resolve(self, step: Step) -> _Resolved:
        body = step.body
        if isinstance(body, InjectBody):
            place = self.place(body.place)
            return _Inject(
                place, tuple(self.token_for(t, place) for t in body.tokens), False
            )
        if isinstance(body, UpdateBody):
            place = self.place(body.place)
            return _Inject(place, (self.token_for(body.token, place),), True)
        if isinstance(body, AdvanceBody):
            return self.advance(body, step.position)
        if isinstance(body, FireBody):
            return self.fire(body)
        if isinstance(body, AssumeGuardBody):
            return self.assume_guard(body, step.position)
        if isinstance(body, AssumePredicateBody):
            return self.assume_predicate(body, step.position)
        return _Expect(tuple(self.condition(c) for c in body.conditions))

    def assume_guard(self, body: AssumeGuardBody, position: Position) -> _Assume:
        transition = self.transition(body.transition)
        guard = self.transitions[transition].guard
        if guard is None:
            raise self.error(
                "SC308",
                f"[{transition}] has no `guard` fact, so there is nothing to "
                f'assume for it (`assume predicate "p"` assumes an arc\'s '
                "predicate handler)",
                position,
            )
        return _Assume(transition, guard, None, body.value)

    def assume_predicate(
        self, body: AssumePredicateBody, position: Position
    ) -> _Assume:
        named = [
            arc.consume.predicate.handler
            for arc in self.net.arcs
            if arc.consume is not None
            and arc.consume.predicate is not None
            and arc.consume.predicate.handler == body.predicate
        ]
        if not named:
            raise self.error(
                "SC310",
                f"no consume arc names predicate handler {json.dumps(body.predicate)} "
                '(`predicate handler "p"` on an arc), so there is nothing to '
                "assume for it",
                position,
                _suggest(body.predicate, self._named_predicates()),
            )
        return _Assume(None, None, body.predicate, body.value)

    def _named_predicates(self) -> Mapping[str, Any]:
        known: dict[str, Any] = {}
        for arc in self.net.arcs:
            consume = arc.consume
            if consume is not None and consume.predicate is not None:
                known[consume.predicate.handler or ""] = True
        return known

    def advance(self, body: AdvanceBody, position: Position) -> _Advance:
        if body.place is not None:
            place = self.place(body.place)
        else:
            clocks = sorted(
                {tr.timer.clock for tr in self.net.transitions if tr.timer is not None}
            )
            if len(clocks) != 1:
                reason = (
                    "no timer names a clock place"
                    if not clocks
                    else "the timers name several clock places: "
                    + ", ".join(f"({c})" for c in clocks)
                )
                raise self.error(
                    "SC208", f"`advance` needs a place here: {reason}", position
                )
            place = clocks[0]
        accepts = self.places[place].accepts
        if len(accepts) != 1:
            raise self.error(
                "SC208",
                f"`advance` needs a clock place of one color; ({place}) takes "
                + ", ".join(accepts),
                position,
            )
        return _Advance(place, accepts[0], body.seconds, body.relative)

    def fire(self, body: FireBody) -> _Fire:
        transition = self.transition(body.transition)
        arcs = [a for a in self.net.arcs if a.to_transition == transition]
        binding_places = {
            cast(str, a.from_place)
            for a in arcs
            if a.consume is not None and a.consume.mode in ("consume", "read")
        }
        withs: list[_With] = []
        for clause in body.withs:
            place = self.place(clause.place)
            if place not in binding_places:
                raise self.error(
                    "SC209",
                    f"[{transition}] binds no token from ({place})",
                    clause.place.position,
                )
            if clause.template is not None:
                token = self.template(clause.template)
                withs.append(_With(place, f"${clause.template.name}", token=token))
            elif clause.index is not None:
                withs.append(_With(place, f"#{clause.index}", index=clause.index))
            else:
                subset = cast(dict[str, Any], clause.subset)
                withs.append(_With(place, _json(subset), subset=subset))
        templates = produce_templates(self.net, transition)
        outputs: dict[int, _Output] = {}
        for clause in body.outputs:
            place = self.place(clause.place)
            here = [i for i, t in enumerate(templates) if t.destination == place]
            if not here:
                raise self.error(
                    "SC210",
                    f"[{transition}] produces nothing into ({place})",
                    clause.place.position,
                )
            fixed = [i for i in here if net_fills(templates[i])]
            open_ = [i for i in here if not net_fills(templates[i])]
            if clause.nothing or clause.merge is not None:
                if fixed and (clause.nothing or not open_):
                    raise _fixed_error(
                        self, transition, templates[fixed[0]], clause.place
                    )
                if len(open_) != 1:
                    raise self.error(
                        "SC210",
                        f"[{transition}] has {len(open_)} outputs into ({place}); "
                        "give the tokens with their colors",
                        clause.place.position,
                    )
                index = open_[0]
                _no_repeat(self, outputs, index, transition, clause.place)
                outputs[index] = (
                    _Output(nothing=True)
                    if clause.nothing
                    else _Output(merge=clause.merge)
                )
                continue
            by_index: dict[int, list[Token]] = {}
            for expr in clause.tokens:
                colors = [templates[i].type for i in here]
                token = self.token_for(expr, place, sorted(set(colors)))
                matches = [i for i in here if templates[i].type == token.type]
                index = matches[0]
                if net_fills(templates[index]):
                    raise _fixed_error(self, transition, templates[index], clause.place)
                by_index.setdefault(index, []).append(token)
            for index, tokens in by_index.items():
                _no_repeat(self, outputs, index, transition, clause.place)
                outputs[index] = _Output(tokens=tuple(tokens))
        return _Fire(transition, tuple(withs), outputs)

    def condition(self, condition: Condition) -> _Condition:
        place = self.place(condition.place) if condition.place is not None else None
        tokens = (
            tuple(self.token_for(t, place) for t in condition.tokens)
            if place is not None
            else ()
        )
        transitions = tuple(self.transition(t) for t in condition.transitions)
        return _Condition(condition, place, tokens, transitions)


def _no_repeat(
    resolver: _Resolver,
    outputs: Mapping[int, _Output],
    index: int,
    transition: str,
    place: NameRef,
) -> None:
    if index in outputs:
        raise resolver.error(
            "SC210",
            f"two `->` clauses give the same output of [{transition}] into "
            f"({place.name})",
            place.position,
        )


def _fixed_error(
    resolver: _Resolver, transition: str, template: ProduceTemplate, place: NameRef
) -> PlayError:
    how = "data cel" if template.cel is not None else "data"
    return resolver.error(
        "SC211",
        f"the net fixes the {template.type} output of [{transition}] into "
        f"({template.destination}) with `{how}`; a play may not give it",
        place.position,
    )


def _suggest(name: str, known: Mapping[str, Any]) -> list[str]:
    close = difflib.get_close_matches(name, list(known), n=3, cutoff=0.6)
    return [f"did you mean: {', '.join(close)}"] if close else []


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _token_text(token: Token) -> str:
    return f"{token.type} {_json(token.data)}"


# ── Loading the net ──────────────────────────────────────────────────────


def _load_reference(path: Path, *, validate_ir: bool = True) -> dict[str, Any]:
    """Compile or read one net or composition document."""
    suffix = path.suffix.lower()
    if suffix == ".petrinet":
        return compile_petrinet_text(
            read_petrinet_text(path),
            str(path),
            net_loader=_reference_loader(path.parent, {}, validate_ir=validate_ir),
            origin=path.parent,
            validate_ir=validate_ir,
        )
    if suffix == ".json":
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"{path.name}: a net document is a JSON object")
        return cast(dict[str, Any], document)
    raise ValueError(f"unsupported net file type {suffix or path.name!r}")


def _reference_loader(
    origin: Path,
    documents: dict[str, dict[str, Any]],
    *,
    validate_ir: bool = True,
) -> Callable[[str], Mapping[str, Any] | Path | str]:
    def load(ref: str) -> Mapping[str, Any] | Path | str:
        path = Path(ref)
        if not path.is_absolute():
            path = origin / path
        document = _load_reference(path, validate_ir=validate_ir)
        documents[ref] = document
        return document

    return load


def load_play_net(play: Play, *, validate_ir: bool = True) -> PlayNet:
    """Resolve the play's ``net`` or ``use``/``wire`` lines (SC201/SC212).

    ``validate_ir=False`` threads the option to the underlying compile
    (see :func:`velocitron_petrinet.compile_petrinet_text`): the
    Contribution IR schema check is skipped, valid nets compile
    identically and faster, and an invalid net fails at a later
    resolution or net-validation error, reported as SC201.
    """
    origin = play.origin or Path(".")
    position = play.net_position or play.position

    def fail(message: str, details: Sequence[str] = ()) -> PlayError:
        return PlayError(
            Diagnostic("SC201", message, play.source, position, tuple(details))
        )

    if play.net is not None and (
        play.uses or play.wires or play.refines or play.shares
    ):
        raise PlayError(
            Diagnostic(
                "SC212",
                "a play names one `net` or composes with `use`, `wire`, "
                "`share` and `refine`, not both",
                play.source,
                play.uses[0].position if play.uses else position,
            )
        )
    if play.net is None and not play.uses:
        raise PlayError(
            Diagnostic(
                "SC212",
                'a play needs `net "file"` or `use "file" as alias` lines',
                play.source,
                play.position,
            )
        )
    documents: dict[str, dict[str, Any]] = {}
    try:
        if play.net is not None:
            label = play.net
            document = _load_reference(origin / play.net, validate_ir=validate_ir)
        else:
            label = ", ".join(f"{use.alias} = {use.ref}" for use in play.uses)
            document = {
                "nets": [{"ref": use.ref, "alias": use.alias} for use in play.uses],
                "wires": [
                    {
                        "from": {"net": wire.from_alias, "port": wire.from_place},
                        "to": {"net": wire.to_alias, "port": wire.to_place},
                    }
                    for wire in play.wires
                ],
                "refinements": [
                    {
                        "net": refine.alias,
                        "transition": refine.transition,
                        "by": refine.by,
                    }
                    for refine in play.refines
                ],
                "shares": [
                    {
                        "places": [
                            {"net": alias, "place": place}
                            for alias, place in share.members
                        ]
                    }
                    for share in play.shares
                ],
            }
            position = play.uses[0].position
        if "nets" not in document:
            net = parse_net(document)
            return PlayNet(
                net=net,
                label=label,
                document=document,
                place_names={place.name: place.name for place in net.places},
                decorations=read_decorations(document),
                composed=False,
            )
        net_origin = (origin / play.net).parent if play.net else origin
        composition = parse_composition(
            document,
            origin=net_origin,
            net_loader=_reference_loader(
                net_origin, documents, validate_ir=validate_ir
            ),
        )
    except PetrinetDslError as error:
        raise fail("the net does not compile", [error.diagnostic.render()]) from error
    except (NetValidationError, OSError, UnicodeError, ValueError) as error:
        raise fail(f"the net cannot be loaded: {error}") from error
    try:
        net = merge_composition(composition)
    except MergeNetValidationError as error:
        raise NetValidationError(str(error)) from error
    validate_net(net)
    parsed = cast(dict[str, Net], composition.parsed_nets)
    fusion = port_fusion_map(parsed, composition.wires, composition.shares)
    place_names = {place.name: place.name for place in net.places}
    place_names.update(fusion)
    sources = composition.sources or {}
    raw_by_alias = {
        alias: documents.get(sources.get(alias, ""), {}) for alias in parsed
    }
    refined = {f"{r.net}.{r.transition}": r.by for r in composition.refinements}
    return PlayNet(
        net=net,
        label=label,
        document=None,
        place_names=place_names,
        decorations=_composed_decorations(parsed, raw_by_alias, fusion, refined),
        composed=True,
        refined=refined,
    )


def _composed_decorations(
    parsed: Mapping[str, Net],
    raw_by_alias: Mapping[str, Mapping[str, Any]],
    fusion: Mapping[str, str],
    refined: Mapping[str, str],
) -> Decorations:
    """Each constituent's decorations, renamed the way the merge renames.

    The merge appends each constituent's arcs in alias order and leaves out
    the arcs of refined transitions, so an arc decoration moves to the
    index its arc has among the kept arcs. A fused place keeps the first
    member's decoration; a refined transition's decorations are dropped.
    """
    nodes: dict[str, Decoration] = {}
    arcs: dict[int, Decoration] = {}
    quiet: set[str] = set()
    shown: dict[str, tuple[str, ...]] = {}
    offset = 0
    for alias, net in parsed.items():
        decorations = read_decorations(raw_by_alias.get(alias, {}))
        for key, decoration in decorations.nodes.items():
            kind, _, name = key.partition(":")
            qualified = f"{alias}.{name}"
            if kind == "transition" and qualified in refined:
                continue
            target = fusion.get(qualified, qualified) if kind == "place" else qualified
            nodes.setdefault(f"{kind}:{target}", decoration)
        merged_index: dict[int, int] = {}
        for index, arc in enumerate(net.arcs):
            if f"{alias}.{arc.to_transition or arc.from_transition}" not in refined:
                merged_index[index] = offset + len(merged_index)
        for index, decoration in decorations.arcs.items():
            if index in merged_index:
                arcs[merged_index[index]] = decoration
        quiet |= decorations.quiet_colors
        for color, fields in decorations.shown_fields.items():
            shown.setdefault(color, fields)
        offset += len(merged_index)
    return Decorations(
        nodes=nodes, arcs=arcs, quiet_colors=frozenset(quiet), shown_fields=shown
    )


def _starting_marking(play: Play, subject: PlayNet) -> Marking:
    choice = play.marking
    if choice == "none":
        return Marking()
    if choice == "initial":
        return subject.net.initial_marking or Marking()
    position = play.marking_position or play.position
    document = subject.document
    markings: Mapping[str, Any] = {}
    if document is not None:
        payload = cast(
            Mapping[str, Any],
            cast(Mapping[str, Any], document.get("annotations") or {}).get(
                "petrinet.dsl/v1"
            )
            or {},
        )
        markings = cast(Mapping[str, Any], payload.get("markings") or {})
    if choice not in markings:
        available = ", ".join(sorted(markings)) or "none"
        raise PlayError(
            Diagnostic(
                "SC206",
                f"the net has no named marking {choice} (named markings: {available})",
                play.source,
                position,
            )
        )
    raw = cast(Mapping[str, Sequence[Mapping[str, Any]]], markings[choice])
    return Marking(
        {
            place: [Token(cast(str, t["type"]), dict(t["data"])) for t in tokens]
            for place, tokens in raw.items()
        }
    )


def _with_kept_records(
    play: Play, subject: PlayNet, resolver: _Resolver, marking: Marking
) -> Marking:
    """``marking`` with each kept record at its start (ADR 0051).

    A start that reads the instance is built from the story's ``instance``
    token; with none, the story starts without that record and may inject it.
    """
    instance: dict[str, Any] | None = None
    expr = play.instance
    if expr is not None:
        instance = (
            resolver.template(expr).data if isinstance(expr, NameRef) else expr.data
        )
    position = play.instance_position or play.position
    for name, record in sorted(kept_records(subject.net).items()):
        if record.reads_instance and instance is None:
            continue
        try:
            token = Token(record.color, build_start(record, instance))
        except KeptStartError as error:
            raise PlayError(
                Diagnostic("SC215", str(error), play.source, position)
            ) from error
        violation = domain_violation(subject.net, name, token)
        if violation is not None:
            raise PlayError(
                Diagnostic(
                    "SC215",
                    f"the start of ({name}) breaks a domain: {violation}",
                    play.source,
                    position,
                )
            )
        marking = marking.set(name, [token])
    return marking


# ── Playback ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _PlannedStep:
    step: Step
    path: str
    resolved: _Resolved


class _StepFailed(Exception):
    def __init__(self, failure: StepFailure) -> None:
        super().__init__(failure.diagnostic.message)
        self.failure = failure


def _engine(registry: HandlerRegistry) -> Engine:
    """An engine with the CEL adapter this package selects.

    ``velocitron_engine.Engine`` requires an adapter. Pass
    ``get_default_adapter`` from ``velocitron_cel``.
    """
    return Engine(registry, cel_adapter=get_default_adapter())


def check_play(
    play: Play, *, paths: Sequence[str] | None = None, validate_ir: bool = True
) -> PlayReport:
    """Resolve ``play`` and play each path (all, or the named ones).

    Raises :class:`PlayError` for a play that cannot be resolved
    (``SC2xx``), including an unknown path name. Never raises for a step
    that fails: the trace of that path ends in a :class:`StepFailure`.
    Deterministic, and reads no clock.
    """
    subject = load_play_net(play, validate_ir=validate_ir)
    colors = {color for place in subject.net.places for color in place.accepts}
    for show in play.shows:
        if show.color not in colors:
            raise PlayError(
                Diagnostic(
                    "SC214",
                    f"`show` names color {show.color}, which no place takes "
                    f"(colors: {', '.join(sorted(colors))})",
                    play.source,
                    show.position,
                )
            )
    resolver = _Resolver(play, subject)
    resolved = {
        path.name: [_PlannedStep(s, path.name, resolver.resolve(s)) for s in path.steps]
        for path in play.paths
    }
    initial = _with_kept_records(
        play, subject, resolver, _starting_marking(play, subject)
    )
    plans = _path_plans(play, resolved)
    selected = list(paths) if paths else [path.name for path in play.paths]
    for name in selected:
        if play.path(name) is None:
            raise PlayError(
                Diagnostic(
                    "SC213",
                    f"the play has no path {name} "
                    f"(paths: {', '.join(p.name for p in play.paths)})",
                    play.source,
                    play.position,
                )
            )
    traces: list[PlayTrace] = []
    for name in selected:
        path = cast(PlayPath, play.path(name))
        plan, inherited = plans[name]
        # A path plays on its own registry: an `assume` step registers stub
        # handlers for the rest of the path, and one path's assumptions must
        # never bleed into another's playback.
        registry = HandlerRegistry()
        engine = _engine(registry)
        traces.append(
            _play(play, subject, engine, registry, path, plan, inherited, initial)
        )
    return PlayReport(play, subject, tuple(traces))


def _path_plans(
    play: Play, resolved: Mapping[str, list[_PlannedStep]]
) -> dict[str, tuple[list[_PlannedStep], int]]:
    """Each path's full step list (inherited prefix first) and prefix length."""
    labels: dict[str, tuple[str, int]] = {}
    plans: dict[str, tuple[list[_PlannedStep], int]] = {}
    for path in play.paths:
        prefix: list[_PlannedStep] = []
        if path.from_label is not None:
            found = labels.get(path.from_label.name)
            if found is None:
                later = any(
                    step.label == path.from_label.name
                    for other in play.paths
                    for step in other.steps
                )
                raise PlayError(
                    Diagnostic(
                        "SC205",
                        f"no step @{path.from_label.name} before path {path.name}"
                        + (
                            "; a path branches from the trunk or an earlier path"
                            if later
                            else ""
                        ),
                        play.source,
                        path.from_label.position,
                    )
                )
            owner, position = found
            prefix = plans[owner][0][: position + 1]
        full = [*prefix, *resolved[path.name]]
        plans[path.name] = (full, len(prefix))
        for offset, step in enumerate(path.steps):
            if step.label is not None:
                labels[step.label] = (path.name, len(prefix) + offset)
    return plans


def _play(
    play: Play,
    subject: PlayNet,
    engine: Engine,
    registry: HandlerRegistry,
    path: PlayPath,
    plan: Sequence[_PlannedStep],
    inherited: int,
    initial: Marking,
) -> PlayTrace:
    marking = initial
    results: list[StepResult] = []
    failure: StepFailure | None = None
    player = _Player(play, subject, engine, registry)
    for index, planned in enumerate(plan):
        if index < inherited and isinstance(planned.resolved, _Assume):
            # A replayed prefix carries its assumptions: scope them again on
            # this path's registry before the prefix replays (the prefix's
            # guard consults come later in this loop, on the same registry).
            player.assume(planned, planned.resolved, index, marking)
            continue
        try:
            result = player.play(planned, index, marking)
        except _StepFailed as failed:
            failure = failed.failure
            break
        results.append(result)
        marking = result.after
    return PlayTrace(
        play=play,
        subject=subject,
        path=path,
        initial=initial,
        steps=tuple(results),
        failure=failure,
        inherited=inherited,
    )


def _stamp_matured_by(
    records: Sequence[FiringRecord | InjectionRecord], injection_id: str
) -> None:
    """Mark the firing records a clock move matured.

    An injection record has no ``metadata``. Only a firing does, so the
    stamp narrows to that arm before writing ``maturedBy``.
    """
    for record in records:
        if "firingId" not in record:
            continue
        record.setdefault("metadata", {})["maturedBy"] = injection_id


class _Player:
    # A safety cap for one advance statement's maturation loop: one clock
    # step may mature a bounded batch of deadlines (the engine's own
    # selection cap is per-`advance`); a play whose maturation does not
    # quiesce within this many firings raises SC315 rather than hanging
    # or returning a truncated result.
    _ADVANCE_MAX_MATURING: int = 1000

    def __init__(
        self,
        play: Play,
        subject: PlayNet,
        engine: Engine,
        registry: HandlerRegistry,
    ) -> None:
        self.source = play
        self.net = subject.net
        self.engine = engine
        self.registry = registry
        self.priorities = {tr.name: tr.priority or 0 for tr in subject.net.transitions}
        self.kept = frozenset(kept_records(subject.net))

    def fail(
        self,
        planned: _PlannedStep,
        index: int,
        before: Marking,
        code: str,
        message: str,
        details: Sequence[str] = (),
        **extra: Any,
    ) -> _StepFailed:
        step = planned.step
        diagnostic = Diagnostic(
            code,
            message,
            self.source.source,
            step.position,
            tuple(details),
        )
        return _StepFailed(
            StepFailure(
                step=step,
                path=planned.path,
                index=index,
                before=before,
                diagnostic=diagnostic,
                **extra,
            )
        )

    def play(self, planned: _PlannedStep, index: int, marking: Marking) -> StepResult:
        resolved = planned.resolved
        if isinstance(resolved, _Inject):
            return self.inject(planned, resolved, index, marking)
        if isinstance(resolved, _Advance):
            return self.advance(planned, resolved, index, marking, play_attempt=0)
        if isinstance(resolved, _Fire):
            return self.fire(planned, resolved, index, marking, play_attempt=0)
        if isinstance(resolved, _Assume):
            return self.assume(planned, resolved, index, marking)
        return self.expect(planned, resolved, index, marking)

    def base(
        self, planned: _PlannedStep, index: int, before: Marking, **kw: Any
    ) -> StepResult:
        records = kw.get("records")
        if records is not None and "markings" not in kw:
            kw["markings"] = self._record_markings(self.net, before, records)
        return StepResult(
            step=planned.step,
            path=planned.path,
            index=index,
            before=before,
            **kw,
        )

    @staticmethod
    def _record_markings(
        net: Net, before: Marking, records: tuple[FiringRecord | InjectionRecord, ...]
    ) -> tuple[Marking, ...]:
        """One marking per record: how the net looks after that record alone.

        Replayed from the records up to and including each one, starting from
        the step's ``before``, with no handlers invoked — the same firing
        and injection tape ``velocitron_journal.replay_events`` folds (D5's
        test convenience). The last entry is the step's ``after``: the check
        loop's records are the step's own marking effects. Journal storage
        stays in the language implementation; this fold is the checker's.
        """
        return markings_after_records(net, before, records)

    def assume(
        self, planned: _PlannedStep, resolved: _Assume, index: int, marking: Marking
    ) -> StepResult:
        """Scope an assumption: from this step on, the stub answers every
        consult until the path ends or the next assume for the same
        transition (guard) or the same ref (predicate) replaces it."""
        if resolved.transition is not None:
            self.registry.register_guard(
                cast(str, resolved.guard_ref),
                lambda inp, _value=resolved.value: _value,
            )
        else:
            self.registry.register_predicate(
                cast(str, resolved.predicate_ref),
                lambda inp, _value=resolved.value: _value,
            )
        return self.base(planned, index, marking, after=marking)

    def inject(
        self, planned: _PlannedStep, resolved: _Inject, index: int, marking: Marking
    ) -> StepResult:
        place = resolved.place
        count = len(resolved.tokens)
        if (
            not resolved.replace
            and place in self.kept
            and (marking.get(place) or count > 1)
        ):
            raise self.fail(
                planned,
                index,
                marking,
                "SC305",
                f"the injection is rejected: ({place}) is a kept record and already "
                "holds its record; change it with `update`"
                if marking.get(place)
                else f"the injection is rejected: ({place}) is a kept record and "
                "holds one record",
            )
        try:
            if resolved.replace:
                after, record = self.engine.inject_token(
                    self.net,
                    marking,
                    resolved.place,
                    resolved.tokens[0],
                    attempt=index,
                    replace=True,
                )
                records: list[InjectionRecord] = [record]
            else:
                after, records = self.engine.inject_tokens(
                    self.net,
                    marking,
                    [(resolved.place, token) for token in resolved.tokens],
                    attempt=index,
                )
        except ValueError as error:
            raise self.fail(
                planned, index, marking, "SC305", f"the injection is rejected: {error}"
            ) from error
        replaced = [t for r in records for t in r["replaced"]]
        return self.base(
            planned,
            index,
            marking,
            after=after,
            records=tuple(records),
            produced={resolved.place: list(resolved.tokens)},
            replaced={resolved.place: replaced} if replaced else {},
        )

    def advance(
        self,
        planned: _PlannedStep,
        resolved: _Advance,
        index: int,
        marking: Marking,
        play_attempt: int = 0,
    ) -> StepResult:
        current = marking.get(resolved.place)
        token = current[0] if current else None
        if resolved.relative:
            now = token.data.get("now") if token is not None else None
            if not isinstance(now, (int, float)) or isinstance(now, bool):
                found = (
                    f"({resolved.place}) is empty"
                    if token is None
                    else f"its token is {_token_text(token)}"
                )
                raise self.fail(
                    planned,
                    index,
                    marking,
                    "SC306",
                    f"`{planned.step.statement}` adds to the clock's `now`, but "
                    f"{found}",
                )
            value = now + resolved.seconds
        else:
            value = resolved.seconds
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        data = dict(token.data) if token is not None else {}
        data["now"] = value
        new = Token(token.type if token is not None else resolved.color, data)
        after, record = self.engine.inject_token(
            self.net, marking, resolved.place, new, attempt=index, replace=True
        )
        replaced = list(record["replaced"])
        result = self.base(
            planned,
            index,
            marking,
            after=after,
            records=(record,),
            produced={resolved.place: [new]},
            replaced={resolved.place: replaced} if replaced else {},
        )
        if not replaced and not marking.get(resolved.place, ()):
            # An absolute settle on an empty clock place: update-only — the
            # statement is allowed where no firing can mature (ADR 0060 D4).
            return result
        records: list[FiringRecord | InjectionRecord] = [record]
        # The maturation pass: the statement plays every firing of a
        # timer-gated transition the new time enabled, to quiescence, under
        # the net's priority policy — what ``Engine.advance`` does for the
        # engine seam (ADR 0060 D4), symbolically: the play supplies output
        # data by the same rules a `fire` step does, priority PINNED and the
        # checker registering no handlers (so the candidate set is narrowed
        # to the transitions whose outputs the play can determine — the
        # SC303 skip rule — and the policy picks among those). A failing
        # firing is recorded as the step's evidence and the pass continues
        # without that transition — the engine seam's failure budget
        # exhausts a persistently failing transition (ADR 0015); the play,
        # which has no budget seam, excludes the failing transition from the
        # rest of this pass instead — the pass never spins on it. Each
        # firing record the pass extends carries ``maturedBy`` — the clock
        # injection's ``injectionId`` — so a reader tells a firing the
        # reader clicked from one the clock move matured.
        fired = 0
        failed_transitions: set[str] = set()
        while True:
            candidates = [
                name
                for name in self.engine.enabled_transitions(
                    self.net, after, attempt=index + fired
                )
                if name in self._timed_on(resolved.place)
                and name not in failed_transitions
                and self._outputs_determined(name, after, index + fired)
            ]
            if not candidates:
                break
            policy = self.engine.registry.resolve_firing_policy(PRIORITY_FIRING_POLICY)
            choice = policy(
                FiringPolicyInput(
                    marking=after,
                    enabledTransitions=candidates,
                    priorities={
                        name: self.priorities.get(name, 0) for name in candidates
                    },
                    consecutiveFailures={name: 0 for name in candidates},
                )
            )
            if choice is None:
                break
            fired += 1
            if fired >= self._ADVANCE_MAX_MATURING:
                raise self.fail(
                    planned,
                    index,
                    after,
                    "SC315",
                    "the advance's maturation did not quiesce: it hit the cap "
                    f"of {self._ADVANCE_MAX_MATURING} matured firings, so the "
                    "play is unbounded",
                )
            resolved_fire = _Fire(transition=choice, withs=(), outputs={})
            synthetic = _PlannedStep(
                Step(
                    kind="fire",
                    body=FireBody(
                        transition=NameRef(choice, Position(0, 0)),
                        withs=(),
                        outputs=(),
                    ),
                    statement=f"fire [{choice}]",
                    position=Position(0, 0),
                ),
                planned.path,
                resolved_fire,
            )
            try:
                maturing = self.fire(
                    synthetic,
                    resolved_fire,
                    index,
                    after,
                    play_attempt=fired,
                )
            except _StepFailed:
                # A raised maturation failure (SC302 and its kindred) happens
                # before a firing record exists. Deposit violations do not
                # take this path: with a play attempt they return a failed
                # record (below). Exclude the transition and keep playing
                # what else the new time matured.
                failed_transitions.add(choice)
                continue
            after = maturing.after
            _stamp_matured_by(maturing.records, str(record["injectionId"]))
            records.extend(maturing.records)
            if maturing.records[-1].get("status") == "failed":
                # The firing dropped a failed record through the deposit
                # path (see `fire`'s settle-time branch); exclude the
                # failing transition from the rest of this pass, exactly as
                # a raised failure would be excluded.
                failed_transitions.add(choice)
        return self.base(
            planned,
            index,
            marking,
            after=after,
            records=tuple(records),
            produced={resolved.place: [new]},
            replaced={resolved.place: replaced} if replaced else {},
        )

    def _failed_firing(
        self, reservation: FiringReservation, error: DepositViolation
    ) -> FiringRecord:
        """The failed firing record a settle-time failure leaves behind.

        The engine-side shape of a deposit violation (D3's record-then-drop,
        what ``Engine.advance`` continues from): the tentative consume
        rolled back — the caller plays the reservation's ``original_marking``
        — and a ``failed`` record with the violation as its error. Emitted
        through the deposit-violation hook so a journal attached to the
        checker's engine sees the same stream the engine seam would write.
        """
        record: FiringRecord = {
            "firingId": reservation.context["firingId"],
            "netId": self.net.name,
            "transition": reservation.transition,
            "attempt": reservation.attempt,
            "status": "failed",
            "inputTokens": reservation.input_tokens,
            "outputTokens": {},
            "error": HandlerError(type="DepositViolation", message=str(error)),
            "metadata": {},
            "timestamps": reservation.context["timestamps"],
        }
        journal = self.engine.journal
        if journal is not None:
            journal.record_deposit_violation(record)
        return record

    def _outputs_determined(
        self, transition: str, marking: Marking, attempt: int
    ) -> bool:
        """Whether every produce template of ``transition`` can be played
        without guessing, the engine's symbolic-advance judgement
        (``velocitron_engine.symbolic_outputs``): the net fills it (``data``
        / ``data cel``), or, for a transition with no ``handler`` fact, a
        consume-mode token of the template's color is available to carry
        (SC303's own line, evaluated up front so an undetermined matured
        firing is skipped, not failed). A handler transition's carried token
        would be a guess at what its handler writes, so it is left for the
        author's own ``fire`` step.

        The judgement must be about the set that would FIRE, so the probe
        takes a real reservation at the firing's own ``attempt``. An
        attempt-branched guard or a guard that raises at some attempts reads
        the same ``firingContext.attempt`` the firing sees, and the
        not-enabled posture (``None``, D9) is a skip, the same attribution a
        real not-enabled transition gets. Read tokens never carry, so a
        transition that only reads its output color is undetermined — the
        same verdict the carry rule reaches at settle time. The reservation
        is released immediately; the marking is untouched.
        """
        if not produce_templates(self.net, transition):
            return True
        reservation = self.engine.reserve(
            self.net, marking, transition, attempt=attempt
        )
        if reservation is None:
            return False
        try:
            return symbolic_outputs(self.net, reservation) is not None
        finally:
            self.engine.unreserve(marking, reservation)

    def _timed_on(self, clock: str) -> frozenset[str]:
        """Transitions whose timer reads ``clock`` — the ones the new time
        can mature. Plain (untimed) firings are not the advance's records:
        they are authored as `fire` steps."""
        return frozenset(
            tr.name
            for tr in self.net.transitions
            if tr.timer is not None and tr.timer.clock == clock
        )

    def fire(
        self,
        planned: _PlannedStep,
        resolved: _Fire,
        index: int,
        marking: Marking,
        play_attempt: int = 0,
    ) -> StepResult:
        transition = resolved.transition
        choose = self.chooser(planned, resolved, index, marking)
        reservation = self.engine.reserve(
            self.net, marking, transition, attempt=index + play_attempt, choose=choose
        )
        if reservation is None:
            explanation = self.engine.explain_enablement(
                self.net, marking, transition, attempt=index + play_attempt
            )
            enabled = tuple(
                self.engine.enabled_transitions(
                    self.net, marking, attempt=index + play_attempt
                )
            )
            enabled_line = "enabled now: " + (
                ", ".join(f"[{name}]" for name in enabled) or "nothing"
            )
            if explanation.enabled:
                wanted = ", ".join(
                    f"with ({w.place}) {w.describe}" for w in resolved.withs
                )
                viable = [
                    "viable binding: "
                    + "; ".join(
                        f"({place}) "
                        + ", ".join(_token_text(t) for t in binding.get(place, ()))
                        for place in dict.fromkeys(w.place for w in resolved.withs)
                    )
                    for binding in explanation.viable
                ]
                raise self.fail(
                    planned,
                    index,
                    marking,
                    "SC302",
                    f"no enabled binding of [{transition}] matches {wanted}",
                    [*viable, enabled_line],
                    explanation=explanation,
                    enabled=enabled,
                )
            details: list[str] = []
            for reason in explanation.reasons:
                details.append(reason.message)
                details.extend(f"  {line}" for line in reason.details)
            details.append(enabled_line)
            raise self.fail(
                planned,
                index,
                marking,
                "SC301",
                f"[{transition}] is not enabled",
                details,
                explanation=explanation,
                enabled=enabled,
            )
        templates = produce_templates(self.net, transition)
        consumed = reservation.consumed_tokens
        carry_by_color: dict[str, list[Token]] = {}
        for tokens in consumed.values():
            for token in tokens:
                carry_by_color.setdefault(token.type, []).append(token)
        output_tokens: dict[str, list[Token]] = {}
        sources: list[OutputSource] = []
        for template_index, template in enumerate(templates):
            if net_fills(template):
                sources.append(OutputSource(template.destination, template.type, "net"))
                continue
            output = resolved.outputs.get(template_index)
            carry = carry_by_color.get(template.type, [])
            if output is not None and output.nothing:
                sources.append(
                    OutputSource(template.destination, template.type, "nothing")
                )
                continue
            if output is not None and output.tokens:
                output_tokens.setdefault(template.destination, []).extend(output.tokens)
                sources.append(
                    OutputSource(template.destination, template.type, "play")
                )
                continue
            if len(carry) != 1:
                raise self.undetermined(
                    planned,
                    index,
                    marking,
                    transition,
                    template,
                    carry,
                    consumed,
                    output,
                )
            data = deepcopy(carry[0].data)
            rule: OutputRule = "carry"
            if output is not None and output.merge is not None:
                data.update(deepcopy(output.merge))
                rule = "merge"
            output_tokens.setdefault(template.destination, []).append(
                Token(template.type, data)
            )
            sources.append(OutputSource(template.destination, template.type, rule))
        out = TransitionHandlerOutput(
            status="completed", outputTokens=output_tokens, error=None, metadata={}
        )
        try:
            after, record = self.engine.settle(
                reservation.reserved_marking, reservation, out
            )
        except DepositViolation as error:
            if play_attempt:
                # A maturation firing's deposit violation plays through as a
                # failed record (the engine's record-then-drop shape, D3):
                # the caller reads the record's failed status and excludes
                # the transition from the rest of the pass.
                after, record = (
                    reservation.original_marking,
                    self._failed_firing(reservation, error),
                )
            else:
                raise self.fail(
                    planned,
                    index,
                    marking,
                    "SC304",
                    f"the engine rejects the deposit of [{transition}]: {error}",
                ) from error
        read = _multiset_difference(reservation.input_tokens, consumed)
        return self.base(
            planned,
            index,
            marking,
            after=after,
            records=(record,),
            binding=reservation.input_tokens,
            consumed=consumed,
            read=read,
            produced=record["outputTokens"],
            outputs=tuple(sources),
        )

    def chooser(
        self, planned: _PlannedStep, resolved: _Fire, index: int, marking: Marking
    ) -> Callable[[Mapping[str, Sequence[Token]]], bool] | None:
        if not resolved.withs:
            return None
        wanted: list[tuple[str, Callable[[Token], bool]]] = []
        for clause in resolved.withs:
            if clause.index is not None:
                tokens = list(marking.get(clause.place, ()))
                if clause.index >= len(tokens):
                    raise self.fail(
                        planned,
                        index,
                        marking,
                        "SC302",
                        f"({clause.place}) holds {len(tokens)} tokens; "
                        f"#{clause.index} counts from 0",
                    )
                chosen = tokens[clause.index]
                wanted.append((clause.place, lambda t, c=chosen: t == c))
            elif clause.token is not None:
                wanted.append((clause.place, lambda t, c=clause.token: t == c))
            else:
                subset = cast(dict[str, Any], clause.subset)
                wanted.append((clause.place, lambda t, s=subset: _contains(t.data, s)))

        def choose(binding: Mapping[str, Sequence[Token]]) -> bool:
            return all(
                any(match(token) for token in binding.get(place, ()))
                for place, match in wanted
            )

        return choose

    def undetermined(
        self,
        planned: _PlannedStep,
        index: int,
        marking: Marking,
        transition: str,
        template: ProduceTemplate,
        carry: Sequence[Token],
        consumed: Mapping[str, Sequence[Token]],
        output: _Output | None,
    ) -> _StepFailed:
        colors = sorted({t.type for tokens in consumed.values() for t in tokens})
        if output is not None and output.merge is not None:
            message = (
                f"`-> ({template.destination}) +{{...}}` has no {template.type} "
                f"token to merge over: [{transition}] consumes {len(carry)} "
                f"{template.type} tokens, and a merge needs exactly one"
            )
        else:
            message = (
                f"the {template.type} output of [{transition}] into "
                f"({template.destination}) is not determined"
            )
        return self.fail(
            planned,
            index,
            marking,
            "SC303",
            message,
            [
                (
                    "the net gives this output no `data` or `data cel`, the step "
                    f"has no `-> ({template.destination})`, and the carry rule "
                    f"needs exactly one consumed {template.type} token (found "
                    f"{len(carry)}; consumed colors: {', '.join(colors) or 'none'})"
                ),
                f"write `-> ({template.destination}) {template.type} {{...}}`",
            ],
        )

    def expect(
        self, planned: _PlannedStep, resolved: _Expect, index: int, marking: Marking
    ) -> StepResult:
        enabled: list[str] | None = None

        def enabled_now() -> list[str]:
            nonlocal enabled
            if enabled is None:
                enabled = self.engine.enabled_transitions(
                    self.net, marking, attempt=index
                )
            return enabled

        checks = tuple(
            self.evaluate(condition, marking, enabled_now)
            for condition in resolved.conditions
        )
        failed = [check for check in checks if not check.ok]
        if failed:
            raise self.fail(
                planned,
                index,
                marking,
                "SC307",
                "expected "
                + "; ".join(f"`{check.text}`" for check in failed)
                + (" does not hold" if len(failed) == 1 else " do not hold"),
                [f"{check.text}: {check.detail}" for check in failed],
                checks=checks,
            )
        return self.base(planned, index, marking, after=marking, checks=checks)

    def evaluate(
        self,
        condition: _Condition,
        marking: Marking,
        enabled_now: Callable[[], list[str]],
    ) -> CheckResult:
        kind = condition.source.kind
        text = condition.source.text
        if condition.place is not None:
            tokens = list(marking.get(condition.place, ()))
            holds = (
                f"({condition.place}) holds "
                + ", ".join(_token_text(t) for t in tokens)
                if tokens
                else f"({condition.place}) is empty"
            )
            if kind == "equals":
                ok = _same_multiset(tokens, list(condition.tokens))
            elif kind == "empty":
                ok = not tokens
            elif kind == "count":
                ok = len(tokens) == condition.source.count
                holds = f"({condition.place}) holds {len(tokens)}"
            else:
                (wanted,) = condition.tokens
                ok = any(
                    t.type == wanted.type and _contains(t.data, wanted.data)
                    for t in tokens
                )
            return CheckResult(text, ok, holds, kind)
        enabled = enabled_now()
        enabled_text = "enabled now: " + (
            ", ".join(f"[{name}]" for name in enabled) or "nothing"
        )
        if kind == "enabled":
            missing = [t for t in condition.transitions if t not in enabled]
            reasons = [
                f"[{t}]: {reason.message}"
                for t in missing
                for reason in self.engine.explain_enablement(
                    self.net, marking, t
                ).reasons
            ]
            return CheckResult(
                text, not missing, "; ".join([enabled_text, *reasons]), kind
            )
        if kind == "not-enabled":
            ok = not any(t in enabled for t in condition.transitions)
            return CheckResult(text, ok, enabled_text, kind)
        if kind == "quiescent":
            return CheckResult(text, not enabled, enabled_text, kind)
        policy = self.engine.registry.resolve_firing_policy(PRIORITY_FIRING_POLICY)
        choice = policy(
            FiringPolicyInput(
                marking=marking,
                enabledTransitions=list(enabled),
                priorities={name: self.priorities[name] for name in enabled},
                consecutiveFailures={name: 0 for name in enabled},
            )
        )
        (wanted_transition,) = condition.transitions
        among = ", ".join(f"[{name}]" for name in enabled)
        detail = (
            f"the priority policy picks [{choice}] of {among}"
            if choice is not None
            else "nothing is enabled"
        )
        return CheckResult(text, choice == wanted_transition, detail, kind)


def _contains(data: Any, subset: Any) -> bool:
    """``subset`` is a part of ``data``: objects compare key by key, all else
    by equality."""
    if isinstance(subset, dict) and isinstance(data, dict):
        data_map = cast(dict[str, Any], data)
        return all(
            key in data_map and _contains(data_map[key], value)
            for key, value in cast(dict[str, Any], subset).items()
        )
    return data == subset


def _same_multiset(left: Sequence[Token], right: Sequence[Token]) -> bool:
    remaining = list(right)
    for token in left:
        if token not in remaining:
            return False
        remaining.remove(token)
    return not remaining


def _multiset_difference(
    whole: Mapping[str, Sequence[Token]], part: Mapping[str, Sequence[Token]]
) -> dict[str, list[Token]]:
    result: dict[str, list[Token]] = {}
    for place, tokens in whole.items():
        remaining = list(tokens)
        for token in part.get(place, ()):
            if token in remaining:
                remaining.remove(token)
        if remaining:
            result[place] = remaining
    return result
