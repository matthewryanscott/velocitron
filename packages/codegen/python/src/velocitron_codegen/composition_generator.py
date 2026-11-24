"""The composition generator: a composition `.petrinet` -> Python modules.

One generated module per composition FILE (ADR 0058, Decision 4): the
outer composition's module and every nested composition's module, each
emitting `<Name>Composition` — one member instance per alias, typed per
the refinement rules — `build_registry(merged_net, *, registry=None,
default_lane=None, journal=None) -> Registration` and
`register_members(registry, net, *, prefix, default_lane) -> Net` for the
level above (or the user).

Refinement (see References): one `typing.Protocol` per refined member —
`<Class>Without<T>` naming the member base's public methods minus
`fire_<t>` (and `guard_<t>` if any) — typing the constructor parameter,
PLUS one mixin per refined set, `Refined<T><MemberStem>Mixin` (spelled
`RefinedBorrowMixin` beside `LoanCheckoutNet`), whose
`fire_<t>` raises `RefinedAway`. `merge_nets` removed the refined
transition, so the Engine can never call it through the composition; the
mixin exists only so that

    class MyCheckout(RefinedBorrow, LoanCheckoutNet): ...

is concrete. The composition module imports `RefinedAway` from
`velocitron_codegen`. The class lives in this package, and generated
text imports it from here.

Member method surfaces and hashes come from re-running the single-net
generator on the member in memory (`MEMBER_SHA256` at generation time;
no member hash is checked at registration). Handler refs shared across
members fail generation naming both qualified transitions and their
member files; a declared ref carrying the `velocitron:synth:` spelling
failures by assert — a member ref can never collide by construction
(the parser gives a declared ref only non-colon names) — and this
module's assert stays as the invariant guard the design asks for.

Nesting: each inner composition file is RE-PARSED for its own facts
(`parse_composition` flattens it) and generates its module first; the
outer module imports the inner class.

A multi-member share's declarations are compared on their `kept`
annotation's two fields — `by` (the keeping actor) and `start` (the
start-expression CEL string, both facts of the share DSL's `kept by
... starts as` fact); differing facts warn on stderr (the module still
generates; the merge keeps its precedence winner).

References: ADR 0058 (Decisions 2 and 4). The merged-net binding names
are the ones `parse_composition` records on each member.

This module does not import ``velocitron``. A merged composition is
revalidated with ``velocitron_petrinet.validate_net`` before its digest is
stamped.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, cast

from velocitron_dsl import lower_petrinet_text
from velocitron_engine import Composition, Net, Place
from velocitron_merge import NetValidationError as MergeNetValidationError
from velocitron_merge import merge_composition as _package_merge_composition
from velocitron_merge import port_fusion_map
from velocitron_petrinet import (
    NetValidationError,
    compile_petrinet_text,
    parse_composition,
    parse_net,
    read_petrinet_text,
    validate_net,
)

from .generator import generate_module
from .hash import SYNTH_HANDLER, net_sha256

__all__ = [
    "CompositionCodegenError",
    "CompositionGenerated",
    "REFINED_AWAY",
    "RefinedAway",
    "generate_composition",
    "generate_composition_full",
]

REFINED_AWAY: Final = "RefinedAway"


def _merge_composition(composition: Composition) -> Net:
    """Merge already-parsed nets, then revalidate the result.

    ``velocitron_merge`` does not revalidate and does not parse files.
    ``parse_composition`` fills ``parsed_nets``. The closing check is
    ``validate_net``, the same close ``velocitron_petrinet`` applies after a merge.
    """
    try:
        merged = _package_merge_composition(composition)
    except MergeNetValidationError as exc:
        raise NetValidationError(str(exc)) from exc
    validate_net(merged)
    return merged


class RefinedAway(Exception):
    """The Engine can never raise this through the composition.

    `merge_nets` removed the refined transition, so no merged-net path
    reaches the refined `fire_<t>`; the generated mixin's body exists only
    so a subclass (`class MyCheckout(RefinedBorrow,
    LoanCheckoutNet)`) satisfies the abstract-method contract.
    """


class CompositionCodegenError(Exception):
    """Every composition generation failure collected, one per line."""

    def __init__(self, messages: Sequence[str]) -> None:
        super().__init__("\n".join(messages))
        self.messages = tuple(messages)


class CompositionGenerated:
    """One generated composition module's text and the facts tests count."""

    def __init__(
        self,
        *,
        text: str,
        module_name: str,
        composition_name: str,
        source: str,
        sha256: str,
        member_sha256: dict[str, str],
        transition_count: int,
        members: tuple[tuple[str, str], ...],
        refinements: tuple[tuple[str, str, str], ...],
        warning: str | None = None,
    ) -> None:
        self.text = text
        self.module_name = module_name
        self.composition_name = composition_name
        self.source = source
        self.sha256 = sha256
        self.member_sha256 = member_sha256
        self.transition_count = transition_count
        self.members = members
        self.refinements = refinements
        self.warning = warning


_NON_WORD: Final = re.compile(r"[^A-Za-z0-9]+")


def _camel(*parts: object) -> str:
    """`switch.owner` -> `SwitchOwner`; `net-name` -> `NetName`.

    The same name rule the single-net generator spells (`_camel` there,
    private); composed names read identically without importing it.
    """
    out: list[str] = []
    for part in parts:
        for chunk in _NON_WORD.split(str(part)):
            if chunk:
                out.append(chunk[0].upper() + chunk[1:])
    return "".join(out)


def _net_class_name(name: str) -> str:
    bare = _camel(name)
    return bare if bare.endswith("Net") else bare + "Net"


def _composition_class_name(name: str) -> str:
    return _camel(name) + "Composition"


def _stem_of_class(member_class: str) -> str:
    """`LoanCheckoutNet` -> `LoanCheckout`."""
    return member_class.removesuffix("Net")


def _protocol_name(member_class: str, transition: str) -> str:
    """`LoanCheckoutNet` + `borrow` -> `LoanCheckoutWithoutBorrow`."""
    return _camel(_stem_of_class(member_class), "Without", transition)


def _mixin_name(member_class: str, transition: str) -> str:
    """The Q65 (a) mixin's name: `Refined<T>` — `RefinedBorrow` beside
    `LoanCheckoutNet`. `transition` is unique per member, so
    `Refined<T>` collides only across members refining same-named
    transitions; there the member stem disambiguates (`Refined<T><Stem>`).
    """
    return f"Refined{_camel(transition)}"


def _module_stem(path_value: str) -> str:
    """`a/b/hold-lifecycle.petrinet` -> `hold_lifecycle`."""
    stem = path_value.replace("\\", "/").rsplit("/", 1)[-1]
    return stem.removesuffix(".petrinet").replace("-", "_").replace(" ", "_")


# ── member surface facts ─────────────────────────────────────────────────


class _Member:
    """One `use` line's facts: the alias, the member's file ref, its leaf
    Net or its inner composition, and the leaf's generated-method facts."""

    def __init__(
        self,
        *,
        alias: str,
        source: str,
        net: Net | None = None,
        inner: "_Level | None" = None,
        method_lines: tuple[str, ...] = (),
        excluded_transitions: set[str] | None = None,
    ) -> None:
        self.alias = alias
        self.source = source
        self.net = net
        self.inner = inner
        self.method_lines = method_lines
        # The transitions whose methods vanish for the Protocol (the
        # refined ones — they carry no method anywhere).
        self.excluded_transitions = excluded_transitions or set()

    @property
    def is_inner(self) -> bool:
        return self.inner is not None

    def typeddict_imports(self, *, members_package: str | None) -> list[str]:
        """The member's `*Outputs` TypedDict imports the Protocol (and the
        constructor's annotations) reference; empty for an inner
        composition member (its class name suffices there)."""
        if self.is_inner:
            return []
        assert self.net is not None
        names: list[str] = []
        for transition in self.net.transitions:
            if _produces_any(self.net, transition.name):
                names.append(f"{_camel(transition.name)}Outputs")
        if not names:
            return []
        stem = _module_stem(self.source)
        if members_package is not None:
            module_path = f"{members_package}.{stem}"
        else:
            module_path = f"{stem}_net"
        return [f"from {module_path} import {', '.join(sorted(set(names)))}"]

    def type_annotation(
        self, *, members_package: str | None, composition_path: str
    ) -> tuple[str, str]:
        """(import, annotation) of the member's value type.

        A leaf member: `from <stem>_net import <NetName>` under
        ``members_package=None`` (or `from <package>.<stem> import ...`),
        annotation `<NetName>`.
        An inner composition member: same import scheme, annotation
        `<Name>Composition`.
        """
        if self.is_inner:
            assert self.inner is not None
            class_name = self.inner.composition_class
        else:
            assert self.net is not None
            class_name = _net_class_name(self.net.name)
        stem = _module_stem(self.source)
        if members_package is not None:
            imports = f"from {members_package}.{stem} import {class_name}"
        else:
            imports = f"from {stem}_net import {class_name}"
        return imports, class_name


class _Level:
    """One composition level's generation result."""

    def __init__(
        self,
        *,
        stem: str,
        composition_class: str,
        members: dict[str, _Member],
        member_sha256: dict[str, str],
        transition_count: int,
        member_texts: dict[str, str] | None = None,
    ) -> None:
        self.stem = stem
        self.composition_class = composition_class
        self.members = members
        self.member_sha256 = member_sha256
        self.transition_count = transition_count
        # Every member's own generated-module TEXT, keyed by alias (for
        # the CLI's writes and `--check`; leaf members only — a nested
        # composition member's text its own level carries).
        self.member_texts: dict[str, str] = member_texts or {}


# ── the generation pipeline ──────────────────────────────────────────────


def generate_composition(
    path: str,
    *,
    actor: str | None = None,
    is_async: bool = False,
    members_package: str | None = None,
) -> dict[str, str]:
    """Both pipelines for a composition, then the module texts.

    Generates `{module_stem: text}`: the outer composition module plus
    every nested level's module, so the CLI writes or `--check`s all of
    them at once.

    The two pipelines join by name as the leaf generator does:
    `compile_petrinet_text` gives the composition document the
    contribution IR lowerer saw; `parse_composition` over it (with the
    file-relative member loader) gives the `Composition` the merge and
    the member module reader need. A `use` ref is a `.petrinet` file or
    (nested) a composition `.petrinet`; the loader compiles both.
    """
    path_value = Path(path).resolve()
    text = read_petrinet_text(path_value)
    source_name = path_value.name
    document = compile_petrinet_text(text, source_name)

    base = path_value.parent

    def load_member(ref: str) -> Any:
        member_path = base / ref
        member_text = read_petrinet_text(member_path)
        return compile_petrinet_text(member_text, member_path.as_posix())

    composition = parse_composition(document, origin=base, net_loader=load_member)
    assert composition.name is not None, "the parser requires a name"
    levels: dict[str, tuple[_Level, str]] = {}
    _generate_level(
        composition,
        path_value.as_posix(),
        levels,
        actor=actor,
        is_async=is_async,
        members_package=members_package,
    )
    return {stem: member_text for stem, (_, member_text) in levels.items()}


def generate_composition_full(
    path: str,
    *,
    actor: str | None = None,
    is_async: bool = False,
    members_package: str | None = None,
) -> dict[str, tuple[str, str]]:
    """Everything the CLI writes or checks, keyed by a generation-time key.

    Each entry is `(text, target_dir)` — the module's text and the
    DIRECTORY the module writes beside: a composition level's entry is
    keyed by its stem and targets the composition file's directory; a
    leaf member's entry is keyed `<stem>.<alias>` and targets the
    member's own file's directory. `generate_composition` (the test
    surface) returns only the composition modules' texts.
    """
    path_value = Path(path).resolve()
    text = read_petrinet_text(path_value)
    source_name = path_value.name
    document = compile_petrinet_text(text, source_name)

    base = path_value.parent

    def load_member(ref: str) -> Any:
        member_path = base / ref
        member_text = read_petrinet_text(member_path)
        return compile_petrinet_text(member_text, member_path.as_posix())

    composition = parse_composition(document, origin=base, net_loader=load_member)
    assert composition.name is not None, "the parser requires a name"
    levels: dict[str, tuple[_Level, str]] = {}
    _generate_level(
        composition,
        path_value.as_posix(),
        levels,
        actor=actor,
        is_async=is_async,
        members_package=members_package,
    )
    # The CLI writes and checks: every composition level's own module and
    # every leaf member's module beside its own file.
    targets: dict[str, tuple[str, str]] = {}
    for stem, (level, composition_text) in levels.items():
        targets[stem] = (composition_text, str(Path(path_value).parent))
        for alias, member in level.members.items():
            if member.net is None:
                continue
            targets[f"{stem}.{alias}"] = (
                level.member_texts[alias],
                Path(member.source).parent.as_posix(),
            )
    return targets


def _generate_level(
    composition: Composition,
    path_value: str,
    levels: dict[str, tuple[_Level, str]],
    *,
    actor: str | None,
    is_async: bool,
    members_package: str | None,
) -> _Level:
    """Build one level's members (recursing into nested compositions
    first), hash them, and emit the module text into ``levels``."""
    stem = _module_stem(path_value)
    if stem in levels:
        return levels[stem][0]

    merged = _merge_composition(composition)
    refined_transitions: dict[str, str] = {}
    for refinement in composition.refinements:
        refined_transitions[refinement.net] = refinement.transition

    members: dict[str, _Member] = {}
    member_sha256: dict[str, str] = {}
    member_texts: dict[str, str] = {}

    class _Loader:
        def __init__(self, base_dir: str) -> None:
            self._base = Path(base_dir)

        def read(self, ref: str) -> Path:
            member_path = (self._base / ref).resolve()
            return member_path

    loader = _Loader(str(Path(path_value).parent))

    for ref in composition.nets:
        assert ref.alias is not None
        alias = ref.alias
        written_source = (composition.sources or {}).get(alias, ref.ref)
        if _is_inner_composition_alias(composition, alias):
            member_path = loader.read(written_source)

            def inner_loader(ref: str, _base: Path = member_path.parent) -> Any:
                inner_path = _base / ref
                return compile_petrinet_text(
                    inner_path.read_text(encoding="utf-8"), inner_path.as_posix()
                )

            inner_composition = parse_composition(
                compile_petrinet_text(
                    member_path.read_text(encoding="utf-8"), member_path.as_posix()
                ),
                origin=member_path.parent,
                net_loader=inner_loader,
            )
            inner = _generate_level(
                inner_composition,
                member_path.as_posix(),
                levels,
                actor=actor,
                is_async=is_async,
                members_package=members_package,
            )
            members[alias] = _Member(
                alias=alias,
                source=member_path.as_posix(),
                inner=inner,
            )
            member_sha256[alias] = net_sha256(_merge_composition(inner_composition))
        else:
            member_path = loader.read(written_source)
            leaf_text = member_path.read_text(encoding="utf-8")
            lowered = lower_petrinet_text(leaf_text, member_path.as_posix())
            leaf_net = parse_net(
                compile_petrinet_text(leaf_text, member_path.as_posix())
            )
            # The member's own module: generated for facts AND for --check.
            leaf_module = generate_module(
                leaf_net,
                source=member_path.as_posix(),
                source_name=member_path.as_posix(),
                text=leaf_text,
                contributions=lowered["contributions"],
                actor=actor,
                is_async=is_async,
            )
            refined_here = refined_transitions.get(alias, "")
            leaf_method_lines: list[str] = []
            for transition in leaf_net.transitions:
                if transition.name == refined_here:
                    continue
                params = _consume_read_places(leaf_net, transition.name)
                ret = (
                    f" -> {_camel(transition.name)}Outputs"
                    if _produces_any(leaf_net, transition.name)
                    else " -> None"
                )
                parameter_text = "".join(f", {place}: list[Token]" for place in params)
                leaf_method_lines.append(
                    f"def fire_{transition.name}(self{parameter_text}){ret}: ..."
                )
            members[alias] = _Member(
                alias=alias,
                source=member_path.as_posix(),
                net=leaf_net,
                method_lines=tuple(leaf_method_lines),
                excluded_transitions={refined_here},
            )
            member_sha256[alias] = leaf_module.sha256
            member_texts[alias] = leaf_module.text

    # Shared refs across members: one ref, one transition.
    errors: list[str] = []
    ref_owners: dict[str, list[tuple[str, str]]] = {}
    for alias, member in members.items():
        if member.net is None:
            continue
        for transition in member.net.transitions:
            if transition.handler is None:
                continue
            ref_owners.setdefault(transition.handler, []).append(
                (f"{alias}.{transition.name}", member.source)
            )
    for ref, owners in ref_owners.items():
        if len(owners) > 1:
            where = ", ".join(f"{source}" for _, source in owners)
            qualified = " and ".join(f"[{name}]" for name, _ in owners)
            errors.append(f'handler ref "{ref}" is shared by {qualified} ({where})')
        elif ref.startswith(SYNTH_HANDLER):
            errors.append(f'handler ref "{ref}" uses the synthesized spelling')
    if errors:
        raise CompositionCodegenError(
            [f"{Path(path_value).as_posix()}:0:1: {e}" for e in errors]
        )

    # Multi-member shares: the docstring line, and the kept-facts warning.
    warning = _kept_facts_warning(composition, path_value)
    if warning:
        sys.stderr.write(warning + "\n")

    level = _Level(
        stem=stem,
        composition_class=_composition_class_name(composition.name or stem),
        members=members,
        member_sha256=member_sha256,
        transition_count=len(merged.transitions),
        member_texts=member_texts,
    )
    text = _emit_composition_text(
        composition=composition,
        merged=merged,
        level=level,
        path_value=path_value,
        actor=actor,
        is_async=is_async,
        members_package=members_package,
        warning=warning,
    )
    levels[stem] = (level, text)
    return level


def _repo_relative(path_value: str) -> str:
    """The path as the repo root sees it (the `SOURCE` spelling a CI
    regeneration reproduces); a path outside the repo stays as given.

    The root is the first ancestor holding the repo-root markers
    (`AGENTS.md` beside the `docs/adr` directory), not a counted parent
    count — an installed (non-repo) copy falls back to the path as-is.
    """
    resolved = Path(path_value).resolve()
    root = Path(__file__).resolve()
    # …/packages/codegen/python/src/velocitron_codegen/composition_generator.py:
    # climb until the repo root (AGENTS.md beside docs/adr). An installed
    # copy has neither marker and keeps the path as given.
    for parent in root.parents:
        if (parent / "AGENTS.md").exists() and (parent / "docs" / "adr").is_dir():
            root = parent
            break
    else:
        return resolved.as_posix()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return resolved.as_posix()


def _docstring_line_for_wire(wire: Any, fused_map: Mapping[str, str]) -> str:
    """`wire lifecycle.(gate.sending) -> attempt.(sending)   fused: attempt.ended`."""
    from_ = f"{wire.from_net}.({wire.from_port})"
    to_ = f"{wire.to_net}.({wire.to_port})"
    fused = fused_map.get(f"{wire.from_net}.{wire.from_port}", "??")
    return f"wire {from_} -> {to_}   fused: {fused}"


def _docstring_line_for_share(share: Any, fused_map: Mapping[str, str]) -> str:
    """`share a.(p) ~ b.(q)   fused: a__b__c`; members in declared order."""
    members = [f"{net}.({place})" for net, place in share.members]
    first_q = f"{share.members[0][0]}.{share.members[0][1]}"
    fused = fused_map.get(first_q, "??")
    return f"share {' ~ '.join(members)}   fused: {fused}"


def _docstring_line_for_refinement(refinement: Any) -> str:
    """`refine lifecycle.[outcome.attempt] by attempt   (no method; attempt.* stands in)`."""
    return (
        f"refine {refinement.net}.[{refinement.transition}] by {refinement.by} "
        f"  (no method; {refinement.by}.* stands in)"
    )


def _emit_composition_text(
    *,
    composition: Composition,
    merged: Net,
    level: _Level,
    path_value: str,
    actor: str | None,
    is_async: bool,
    members_package: str | None,
    warning: str | None,
) -> str:
    """The composition module's deterministic text.

    The generated module is hand-shaped rather than exec'd: its runtime
    half (the `build_registry` / `register_members` bodies) is fixed
    boilerplate whose only variation is the members' names; its surface
    (docstring, Protocol, mixin, `__init__`, `MEMBER_SHA256`) is the
    generated part.
    """
    composition_name = composition.name or "composition"
    class_name = level.composition_class
    source_posix = _repo_relative(path_value)
    # The use lines' rebased SOURCE paths, as the members were parsed.
    merged_sha = net_sha256(merged)

    fused_map = port_fusion_map(
        composition.parsed_nets or {}, composition.wires, composition.shares
    )

    # ── imports ─────────────────────────────────────────────────────
    out: list[str] = []
    out.append(f"# Generated by `velocitron codegen` from {source_posix}. Do not edit.")
    out.append("# No `from __future__ import annotations` here: PEP 655's")
    out.append("# TypedDict detection reads the real objects (see the leaf generator).")
    out.append("")
    refined_import_lines: list[str] = []
    if composition.refinements:
        # The mixin's body raises this exception (Q65 (a)); nothing else
        # in the module touches the constant.
        refined_import_lines = [
            "from velocitron_codegen import RefinedAway"
        ]
    protocol_import_lines: list[str] = []
    if composition.refinements:
        protocol_import_lines = [
            "from typing import Protocol",
            "from velocitron_engine import Token",
        ]
    out.extend(refined_import_lines)
    if protocol_import_lines:
        out.extend(protocol_import_lines)
    out.append("")
    out.append("from typing import Literal")
    out.append("")
    out.append("from velocitron_runtime import Engine")
    out.append("from velocitron_netbase import HashMismatch")
    out.append("from velocitron_netbase import Registration, net_document, net_sha256")
    out.append("from velocitron_netbase import VelocitronNet")
    out.append("from velocitron_replay import ReplayCursor")
    out.append("from velocitron_engine import HandlerRegistry")
    out.append("from velocitron_runtime import HandlerSpec")
    out.append("from velocitron_engine import Net")
    out.append("")

    # The refined members' Protocols reference the leaves' own `*Outputs`
    # TypedDicts; each refined leaf's module contributes one import line,
    # found through the refinement's flat alias (`outcome` among this
    # level's members, `lifecycle.outcome` = a nested composition
    # member's own leaf — the import goes to that leaf's own module).
    refined_typeddict_imports: list[str] = []
    for refinement in composition.refinements:
        refined_leaf = (composition.parsed_nets or {}).get(refinement.net)
        if refined_leaf is None:
            continue
        # Only the TypedDicts the Protocol's kept methods reference, PLUS
        # the refined transition's own (the mixin's return names it —
        # pyright's override check keeps the exact return type).
        names = sorted(
            {
                f"{_camel(transition.name)}Outputs"
                for transition in refined_leaf.transitions
                if _produces_any(refined_leaf, transition.name)
            }
        )
        if not names:
            continue
        # The refined leaf's module: the flat alias's LAST segment within
        # the member that holds it (the module stem is that leaf's file).
        owner_source = _leaf_module_source_of(composition, refinement.net)
        stem = _module_stem(owner_source)
        module_path = (
            f"{members_package}.{stem}"
            if members_package is not None
            else f"{stem}_net"
        )
        refined_typeddict_imports.append(
            f"from {module_path} import {', '.join(names)}"
        )
    # ── the replay constructor's imports ride with the member imports;
    # the classmethod's body is in the class emission below.
    replay_class_imports: list[str] = []
    for ref in composition.nets:
        assert ref.alias is not None
        alias = ref.alias
        member = level.members[alias]
        if member.is_inner:
            # An inner composition member: its own composition class
            # carries the `replay(cursor)` classmethod.
            assert member.inner is not None
            replay_class = member.inner.composition_class
        else:
            assert member.net is not None
            leaf_class = _net_class_name(member.net.name)
            replay_class = f"Replay{leaf_class}"
        stem_of_replay = _module_stem(member.source)
        replay_module_path = (
            f"{members_package}.{stem_of_replay}"
            if members_package is not None
            else f"{stem_of_replay}_net"
        )
        replay_class_imports.append(
            f"from {replay_module_path} import {replay_class} as {alias}_replay"
        )
    imports: list[str] = []
    annotation_of: dict[str, str] = {}
    for alias, member in level.members.items():
        import_line, annotation = member.type_annotation(
            members_package=members_package, composition_path=source_posix
        )
        imports.append(import_line)
        annotation_of[alias] = annotation
    imports.extend(refined_typeddict_imports)
    imports.extend(replay_class_imports)
    if imports:
        out.extend(imports)
        out.append("")

    # ── the docstring ───────────────────────────────────────────────
    doc_lines: list[str] = []
    doc_lines.append(f"composition {composition_name}  ({source_posix})")
    doc_lines.append("")
    for wire in composition.wires:  # declaration order
        doc_lines.append(_docstring_line_for_wire(wire, fused_map))
    for share in composition.shares:  # declaration order
        doc_lines.append(_docstring_line_for_share(share, fused_map))
    for refinement in composition.refinements:
        doc_lines.append(_docstring_line_for_refinement(refinement))
    if level.transition_count:
        doc_lines.append("")
        doc_lines.append(f"# {level.transition_count} merged transitions,")
        doc_lines.append(
            "# one method of their member's own module per non-refined one"
        )

    # ── the Protocol per refined member and the per-set mixin ──────
    protocol_blocks: list[str] = []
    mixin_blocks: list[str] = []
    for refinement in composition.refinements:
        # The refinement's member is a FLAT alias (`lifecycle.outcome`):
        # the refined leaf may sit inside a nested composition member.
        # The leaf's Net is in `parsed_nets`; the Protocol + mixin are
        # emitted by the module that DECLARES the refinement, and the
        # user's mixin-first subclass satisfies the nested owner's
        # typed member too (Q65 (a) + ADR open item 4: no generic inner
        # class needed — the inner composition keeps its leaf type).
        refined_leaf = (composition.parsed_nets or {}).get(refinement.net)
        if refined_leaf is None:
            continue
        member_class = _net_class_name(refined_leaf.name)
        refined_transition = refinement.transition
        protocol_name = _protocol_name(member_class, refined_transition)
        excluded = {refined_transition}
        for transition in refined_leaf.transitions:
            if transition.name == refined_transition and transition.guard:
                excluded.add(f"guard_{transition.name}")
        method_surface = _member_public_methods(refined_leaf, excluded)
        protocol_blocks.append(f"class {protocol_name}(Protocol):")
        protocol_blocks.append(
            "    # The member base's public methods minus the refined ones;"
        )
        protocol_blocks.append(
            "    # a hand-written subclass that matches satisfies it by structure."
        )
        protocol_blocks.append("")
        protocol_blocks.extend(f"    {line}" for line in method_surface)
        protocol_blocks.append("")
        # The mixin: fire_<t> raises RefinedAway; the Engine never calls
        # it through the merge (the transition is gone). The signature
        # matches the member base's exactly (Token parameters, the
        # transition's own Outputs TypedDict), so the mixin-first
        # subclass overrides the base consistently.
        params = _consume_read_places(refined_leaf, refined_transition)
        parameter_text = "".join(f", {place}: list[Token]" for place in params)
        mixin_name = _mixin_name(member_class, refined_transition)
        mixin_blocks.append(f"class {mixin_name}:")
        mixin_blocks.append(
            f'    """The refined-`fire_{refined_transition}` mixin (Q65 (a)).'
        )
        mixin_blocks.append("")
        mixin_blocks.append(
            "    Subclass it first, the member net base second: the body raises"
        )
        mixin_blocks.append(
            f"    {REFINED_AWAY} and is never called through the composition —"
        )
        mixin_blocks.append("    the merge removed the transition it fills.")
        mixin_blocks.append('    """')
        mixin_blocks.append("")
        # The refined transition's own `*Outputs` TypedDict IS imported
        # (the mixin's return matches the base's exactly) — pyright's
        # override check keeps the exact return type.
        mixin_blocks.append(
            f"    def fire_{refined_transition}(self{parameter_text}) -> {_camel(refined_transition)}Outputs:"
        )
        mixin_blocks.append(f"        raise {REFINED_AWAY}(")
        mixin_blocks.append(
            f'            f"the composition refines [{refined_transition}]: '
            f'the Engine never fires it"'
        )
        mixin_blocks.append("        )")
        mixin_blocks.append("")
        mixin_blocks.append("")

    # ── the class and its surface ──────────────────────────────────
    out.extend(protocol_blocks)
    out.extend(mixin_blocks)
    out.append(f"class {class_name}:")
    out.append(f'    """{doc_lines[0]}')
    for line in doc_lines[1:]:
        out.append(f"    {line}" if line else "")
    out.append('    """')
    out.append("")
    out.append(f"    SOURCE = {source_posix!r}")
    out.append(f"    SOURCE_SHA256 = {merged_sha!r}")
    out.append("    MEMBER_SHA256: dict[str, str] = {")
    for alias, sha in sorted(level.member_sha256.items()):
        out.append(f"        {alias!r}: {sha!r},")
    out.append("    }")
    out.append("")
    out.append(f"    NET_NAME = {composition_name!r}")
    out.append(f"    ASYNC = {is_async!r}")
    out.append("")

    # The constructor: one typed member per alias in `use` order. A
    # refined member's parameter keeps the leaf base's annotation (the
    # mixin subclass satisfies both the Protocol and the base check); the
    # Protocol itself is emitted for the user's own subclass authoring.
    parameters: list[str] = []
    for ref in composition.nets:
        assert ref.alias is not None
        alias = ref.alias
        member = level.members[alias]
        _, annotation = member.type_annotation(
            members_package=members_package, composition_path=source_posix
        )
        parameters.append(f"{alias}: {annotation}")
    out.append("    def __init__(self, *,")
    for parameter in parameters:
        out.append(f"        {parameter},")
    out.append("    ) -> None:")
    out.append("        # One member instance per alias, as attributes.")
    for ref in composition.nets:
        assert ref.alias is not None
        out.append(f"        self.{ref.alias} = {ref.alias}")
    aliases_tuple = ", ".join(ref.alias or "" for ref in composition.nets)
    out.append(f"        self.members = ({aliases_tuple},)")
    out.append("")

    # ── the runtime body: fixed boilerplate, one block per member ───
    out.append("    def build_registry(")
    out.append("        self,")
    out.append("        merged_net: Net,")
    out.append("        *,")
    out.append("        registry: HandlerRegistry | None = None,")
    out.append("        default_lane: str | None = None,")
    out.append("        journal: object | None = None,")
    out.append("    ) -> Registration:")
    out.append('        """Hash the merged net, register every member, validate once.')
    out.append("")
    out.append("        Only the outermost composition call validates and records")
    out.append("        the net revision; an inner composition's")
    out.append("        ``register_members`` is threaded through with the one copy.")
    out.append('        """')
    out.append("        actual = net_sha256(merged_net)")
    out.append("        if actual != self.SOURCE_SHA256:")
    out.append("            raise HashMismatch(")
    out.append('                f"SOURCE_SHA256 of {type(self).__name__} does not "')
    out.append(
        '                f"match the net {merged_net.name}: regenerate with `velocitron codegen`"'
    )
    out.append("            )")
    out.append(
        "        registry = registry if registry is not None else HandlerRegistry()"
    )
    out.append("        return self.register_members(registry, merged_net,")
    out.append("            prefix='', default_lane=default_lane, journal=journal)")
    out.append("")
    out.append("    def register_members(")
    out.append("        self,")
    out.append("        registry: HandlerRegistry,")
    out.append("        net: Net,")
    out.append("        *,")
    out.append("        prefix: str,")
    out.append("        default_lane: str | None = None,")
    out.append("        journal: object | None = None,")
    out.append("    ) -> Registration:")
    out.append('        """Register every member under ``prefix``; thread the copy.')
    out.append("")
    out.append("        The outermost composition call sets ``prefix=''`` — its")
    out.append("        members' aliases are already prefixed everywhere in the")
    out.append("        merged net — and validates the final copy once.")
    out.append('        """')
    out.append("        copy = net")
    out.append("        specs: dict[str, HandlerSpec] = {}")
    for ref in composition.nets:
        assert ref.alias is not None
        alias = ref.alias
        member = level.members[alias]
        if member.is_inner:
            out.append(f"        registration = self.{alias}.register_members(")
            out.append("            registry, copy,")
            qualified_alias = alias
            out.append(f"            prefix={qualified_alias!r},")
            out.append("            default_lane=default_lane,")
            out.append("        )")
        else:
            # The member's merged-net alias: its own, qualified by the
            # incoming `prefix` (an inner composition's `lifecycle` makes
            # each leaf's `lifecycle.start` — the flattened key the merge
            # wrote).
            out.append(
                f"        leaf_alias = f'{{prefix}}.{alias}' if prefix else {alias!r}"
            )
            out.append(f"        registration = self.{alias}.register_into(")
            out.append("            registry, copy,")
            out.append("            alias=leaf_alias,")
            out.append("            default_lane=default_lane,")
            out.append("            validate=False,")
            out.append("        )")
        out.append("        copy = registration.net")
        out.append("        specs.update(registration.handler_specs)")
    out.append("")
    out.append("        if prefix == '':")
    out.append("            # The outermost call: validate the final copy once,")
    out.append("            # record the net revision once, and return. Under")
    out.append("            # ASYNC the transitions' handlers live in the spec")
    out.append("            # table, not the registry, so the walk skips them —")
    out.append("            # the guards and named predicates still resolve.")
    out.append("            _engine = Engine(registry)")
    out.append("            for transition in copy.transitions:")
    out.append("                if transition.guard is not None:")
    out.append("                    _engine.registry.resolve_guard(transition.guard)")
    out.append("            for arc in copy.arcs:")
    out.append("                consume = arc.consume")
    out.append("                if (")
    out.append("                    consume is not None")
    out.append("                    and consume.predicate is not None")
    out.append("                    and consume.predicate.handler is not None")
    out.append("                ):")
    out.append("                    _engine.registry.resolve_predicate(")
    out.append("                        consume.predicate.handler")
    out.append("                    )")
    out.append("            if not self.ASYNC:")
    out.append("                _engine.validate(copy)")
    out.append("            if journal is not None:")
    out.append("                record_net_revision = getattr(")
    out.append("                    journal, 'record_net_revision', None")
    out.append("                )")
    out.append("                if callable(record_net_revision):")
    out.append("                    record_net_revision(net_document(copy))")
    out.append("        return Registration(")
    out.append("            net=copy, handler_specs=specs, registry=registry")
    out.append("        )")
    out.append("")

    # ── the replay constructor (ADR 0058, Decision 7's item 5) ──────
    # `<Name>Composition.replay(cursor, *, mode, live)`: one replay
    # member per alias, sharing the ONE cursor; an inner composition
    # member through its own `replay(cursor)` (cursor identity holds).
    out.append("    @classmethod")
    out.append("    def replay(")
    out.append("        cls,")
    out.append("        cursor: ReplayCursor,")
    out.append("        *,")
    out.append('        mode: Literal["strict", "compare"] = "strict",')
    out.append("        live: VelocitronNet | None = None,")
    out.append(f'    ) -> "{class_name}":')
    out.append('        """One replay member per alias, sharing the ONE cursor.')
    out.append("")
    out.append("        A leaf member's replay class is its module's emitted")
    out.append("        ``Replay<Net>(ReplayBase, <Net>Net)``; an inner composition")
    out.append("        member replays through its own ``replay(cursor)`` — the")
    out.append("        cursor object's identity holds at every level. ``live`` passes")
    out.append(
        "        through to every member (the compare-mode driver's live class)."
    )
    out.append('        """')
    for ref in composition.nets:
        assert ref.alias is not None
        alias = ref.alias
        member = level.members[alias]
        if member.is_inner:
            # An inner composition member: through its own replay() — the
            # REPLAY composition itself is the member value (its members'
            # cursors and the replay drive live inside it).
            out.append(f"        built_{alias} = {alias}_replay.replay(")
            out.append("            cursor, mode=mode, live=live")
            out.append("        )")
        else:
            out.append(
                f"        built_{alias} = {alias}_replay(cursor, mode=mode, live=live)"
            )
    argument_texts = ", ".join(
        f"{ref.alias} = built_{ref.alias}" for ref in composition.nets
    )
    out.append(f"        return cls({argument_texts})")
    out.append("")
    return "\n".join(out) + "\n"


def _leaf_module_source_of(composition: Composition, flat_alias: str) -> str:
    """A flat alias's leaf net's file source (the member module's stem).

    The composition's `sources` map keys every flattened leaf by its
    flat alias (the parser carries them); a direct member's key is its
    own alias.
    """
    sources = composition.sources or {}
    if flat_alias in sources:
        return sources[flat_alias]
    # not found: the alias itself is the module name; fall back to a
    # sibling spelling by the leaf alias segments joined.
    return f"{flat_alias}.petrinet"


def _is_inner_composition_alias(composition: Composition, alias: str) -> bool:
    """The `use` was a composition when flattened leaf keys name it."""
    parsed_nets = composition.parsed_nets or {}
    return any(key.startswith(f"{alias}.") for key in parsed_nets)


def _consume_read_places(net: Net, transition_name: str) -> list[str]:
    """One parameter per consume/read place, arc order."""
    places: list[str] = []
    for arc in net.arcs:
        if arc.to_transition != transition_name:
            continue
        consume = arc.consume
        if consume is None or consume.mode == "inhibit":
            continue
        if arc.from_place not in places:
            places.append(str(arc.from_place))
    return places


def _produces_any(net: Net, transition_name: str) -> bool:
    return any(
        arc.from_transition == transition_name and arc.produce is not None
        for arc in net.arcs
    )


def _kept_facts_warning(composition: Composition, path_value: str) -> str | None:
    """The warning when a multi-member share's kept facts differ.

    Comparison fields (the close reason's choice): a declaration's
    `Place.annotations["kept"]` mapping's two keys — `by` (the keeping
    actor) and `start.cel` (the start-expression string). Any difference
    in either across a share's member declarations warns once for that
    share, naming the share's merged name and the differing field; the
    merged net keeps its precedence first, and generation proceeds.
    """
    qname_to_place: dict[str, Place] = {}
    for alias, net in (composition.parsed_nets or {}).items():
        for place in net.places:
            qname_to_place[f"{alias}.{place.name}"] = place
    fused = port_fusion_map(
        composition.parsed_nets or {},
        composition.wires,
        composition.shares,
    )
    merge_classes: dict[str, list[str]] = {}
    for member, fused_name in fused.items():
        merge_classes.setdefault(fused_name, []).append(member)
    warnings_out: list[str] = []
    for fused_name, member_names in merge_classes.items():
        if len(member_names) < 2:
            continue
        kepts: list[tuple[str, Mapping[str, Any] | None]] = []
        for name in sorted(member_names):
            place = qname_to_place[name]
            raw = (place.annotations or {}).get("kept")
            kept = cast(Mapping[str, Any], raw) if isinstance(raw, Mapping) else None
            kepts.append((name, kept))
        differing: list[str] = []
        for field in ("by", "start"):
            values = sorted(
                {str(None if kept is None else kept.get(field)) for _, kept in kepts}
            )
            if len(values) > 1:
                differing.append(field)
        if differing:
            declared = "; ".join(f"{n}: {k}" for n, k in kepts)
            warnings_out.append(
                f"share {fused_name}: the declared places disagree on "
                f"{' and '.join(differing)} (kept facts {declared})"
            )
    if not warnings_out:
        return None
    return "\n".join(f"{path_value}: warning: {line}" for line in warnings_out)


def _member_public_methods(
    net: Net,
    excluded: set[str],
) -> list[str]:
    """The member base's public `fire_*` method lines minus the excluded.

    The lines match the generated leaf module's method shapes (the
    signature, the source place parameters with Token types, the return
    TypedDict name) so a subclass that matches the Protocol also matches
    the base. The member's guard methods (one per `guard` fact) are
    excluded when their transition is the refined one — a refined
    transition's guard vanishes with it. The TypedDict name rule is this
    module's `_camel` (the single-net generator spells the same rule).
    """
    lines: list[str] = []
    for transition in net.transitions:
        if transition.name in excluded:
            continue
        params = _consume_read_places(net, transition.name)
        parameter_text = "".join(f", {place}: list[Token]" for place in params)
        outputs = _produces_any(net, transition.name)
        ret = f" -> {_camel(transition.name)}Outputs" if outputs else " -> None"
        lines.append(f"def fire_{transition.name}(self{parameter_text}){ret}: ...")
        if transition.guard is not None:
            lines.append(
                f"def guard_{transition.name}(self{parameter_text}) -> bool: ..."
            )
    return lines
