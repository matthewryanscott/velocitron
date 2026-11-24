"""The proof report: facts, their status, witnesses and counterexamples.

The JSON shape is the contract in spec/proofs.md; the Obsidian report fence
of a later stage renders it. Text rendering is for the command line.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Literal, cast

from velocitron_engine import Token

Status = Literal["proved", "refuted", "unknown"]

REPORT_VERSION = 1


def _tool() -> str:
    """The program and version a saved report names.

    Prefer the CLI distribution when it is installed, so
    ``velocitron --version`` and the report agree. A wheel of this package
    alone uses its own version and still starts with ``velocitron``.
    """
    for dist in ("velocitron-cli", "velocitron-analysis"):
        try:
            return f"velocitron {version(dist)}"
        except PackageNotFoundError:
            continue
    return "velocitron"


TOOL = _tool()
"""The tool that wrote a report, so a saved report says which prover spoke."""


def _token_json(token: Token) -> dict[str, Any]:
    return {"type": token.type, "data": _sorted(token.data)}


def _sorted(value: Any) -> Any:
    """``value`` with every object's keys in order, so the JSON is byte-stable:
    the prover builds token data and markings from sets."""
    if isinstance(value, Mapping):
        items = cast(Mapping[str, Any], value).items()
        return {key: _sorted(item) for key, item in sorted(items)}
    if isinstance(value, (list, tuple)):
        return [_sorted(item) for item in cast(Sequence[Any], value)]
    return value


def token_text(token: Token) -> str:
    return f"{token.type} {json.dumps(token.data, sort_keys=True, ensure_ascii=False)}"


@dataclass(frozen=True)
class Move:
    """One step of a counterexample: a firing, an arrival, an update or a advance."""

    kind: Literal["fire", "inject", "update", "advance"]
    transition: str | None = None
    place: str | None = None
    token: Token | None = None
    binding: tuple[tuple[str, tuple[Token, ...]], ...] = ()
    outputs: tuple[tuple[str, tuple[Token, ...]], ...] = ()

    def key(self, text: Callable[[Token], str] = token_text) -> tuple[Any, ...]:
        """A hashable key; ``text`` must give ``token_text``'s answer."""

        def tokens(groups: Sequence[tuple[str, Sequence[Token]]]) -> tuple[Any, ...]:
            return tuple((p, tuple(text(t) for t in ts)) for p, ts in groups)

        return (
            self.kind,
            self.transition,
            self.place,
            text(self.token) if self.token else None,
            tokens(self.binding),
            tokens(self.outputs),
        )

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind}
        if self.transition is not None:
            payload["transition"] = self.transition
        if self.place is not None:
            payload["place"] = self.place
        if self.token is not None:
            payload["token"] = _token_json(self.token)
        if self.binding:
            payload["binding"] = {
                p: [_token_json(t) for t in ts] for p, ts in sorted(self.binding)
            }
        if self.outputs:
            payload["outputs"] = {
                p: [_token_json(t) for t in ts] for p, ts in sorted(self.outputs)
            }
        return payload

    def text(self) -> str:
        if self.kind == "fire":
            parts = [f"fire [{self.transition}]"]
            for place, tokens in self.outputs:
                parts.append(
                    f"-> ({place}) " + ", ".join(token_text(t) for t in tokens)
                )
            return " ".join(parts)
        assert self.token is not None
        if self.kind == "advance":
            return f"advance ({self.place}) {json.dumps(self.token.data, sort_keys=True)}"
        arrow = "inject" if self.kind == "inject" else "update"
        return f"{arrow} ({self.place}) <- {token_text(self.token)}"


@dataclass(frozen=True)
class Finding:
    """One thing a fact found: a witness, a counterexample, a waiver."""

    kind: str
    summary: str
    witness: Mapping[str, Any] | None = None
    cases: Mapping[str, Any] | None = None
    enabled: tuple[str, ...] = ()
    transition: str | None = None
    path: tuple[Move, ...] = ()
    cycle: tuple[Move, ...] = ()
    marking: Mapping[str, Any] | None = None
    play: str | None = None
    count: int | None = None

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"kind": self.kind, "summary": self.summary}
        if self.witness is not None:
            payload["witness"] = _sorted(self.witness)
        if self.cases is not None:
            payload["cases"] = _sorted(self.cases)
        if self.count is not None:
            payload["count"] = self.count
        if self.enabled:
            payload["enabled"] = list(self.enabled)
        if self.transition is not None:
            payload["transition"] = self.transition
        if self.path:
            payload["path"] = [move.as_json() for move in self.path]
        if self.cycle:
            payload["cycle"] = [move.as_json() for move in self.cycle]
        if self.marking is not None:
            payload["marking"] = _sorted(self.marking)
        if self.play is not None:
            payload["play"] = self.play
        return payload


@dataclass(frozen=True)
class Proof:
    """One fact about the net and what the prover could show about it."""

    fact: Literal["choice", "invariant", "soundness", "refinement"]
    subject: str
    status: Status
    statement: str
    findings: tuple[Finding, ...] = ()
    reason: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict[str, Any])
    assumptions: tuple[str, ...] = ()
    """Bounds the result holds under, beyond the environment model (the
    firing caps of a domains file)."""

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "fact": self.fact,
            "subject": self.subject,
            "status": self.status,
            "statement": self.statement,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.assumptions:
            payload["assumptions"] = list(self.assumptions)
        if self.details:
            payload["details"] = dict(self.details)
        payload["findings"] = [finding.as_json() for finding in self.findings]
        return payload

    def with_findings(self, findings: Sequence[Finding]) -> Proof:
        return replace(self, findings=tuple(findings))


@dataclass(frozen=True)
class ProofReport:
    net: str
    source: str | None
    proofs: tuple[Proof, ...]
    model: Mapping[str, Any]
    exploration: Mapping[str, Any] | None = None
    composition: Mapping[str, Any] | None = None

    @property
    def status(self) -> Status:
        statuses = {proof.status for proof in self.proofs}
        if "refuted" in statuses:
            return "refuted"
        if "unknown" in statuses:
            return "unknown"
        return "proved"

    @property
    def refuted(self) -> bool:
        return self.status == "refuted"

    def as_json(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "version": REPORT_VERSION,
            "tool": TOOL,
            "net": self.net,
            "source": self.source,
            "status": self.status,
            "facts": [proof.as_json() for proof in self.proofs],
            "model": dict(self.model),
        }
        if self.exploration is not None:
            payload["exploration"] = dict(self.exploration)
        if self.composition is not None:
            payload["composition"] = dict(self.composition)
        return payload

    def json(self) -> str:
        return json.dumps(self.as_json(), indent=2, ensure_ascii=False) + "\n"

    def text(self) -> str:
        lines: list[str] = []
        title = f"{self.source} — net {self.net}" if self.source else f"net {self.net}"
        lines.append(title)
        if self.composition is not None:
            nets = cast(Mapping[str, str], self.composition["nets"])
            lines.append(
                "composition of "
                + ", ".join(f"{alias} ({file})" for alias, file in nets.items())
            )
        sections = (
            ("choice", "choice coverage"),
            ("invariant", "place invariants"),
            ("soundness", "soundness"),
            ("refinement", "refinement"),
        )
        for fact, heading in sections:
            proofs = [proof for proof in self.proofs if proof.fact == fact]
            if not proofs:
                continue
            lines.append("")
            lines.append(heading)
            for proof in proofs:
                lines.append(f"  {proof.status.upper():8} {proof.subject}")
                if proof.status != "proved" or proof.fact == "invariant":
                    lines.append(f"           {proof.statement}")
                if proof.reason:
                    lines.append(f"           why unknown: {proof.reason}")
                for assumption in proof.assumptions:
                    lines.append(f"           assumes: {assumption}")
                quiet: dict[tuple[str, tuple[str, ...]], int] = {}
                for finding in proof.findings:
                    if finding.kind in ("resolved", "waived"):
                        key = (finding.kind, finding.enabled)
                        quiet[key] = quiet.get(key, 0) + 1
                        continue
                    lines.extend(_finding_lines(finding))
                for (kind, enabled), boxes in quiet.items():
                    word = (
                        "resolved by priority"
                        if kind == "resolved"
                        else "waived overlap"
                    )
                    names = " + ".join(f"[{n}]" for n in enabled)
                    lines.append(
                        f"    - {word}: {names} ({boxes} case group{'s' if boxes > 1 else ''})"
                    )
        if self.exploration is not None:
            lines.append("")
            explored = self.exploration
            lines.append(
                f"explored {explored['states']} markings, {explored['edges']} moves"
                + (" (state cap hit)" if explored.get("capped") else "")
            )
            made = cast(Mapping[str, Any] | None, explored.get("madeBy"))
            if made is not None:
                lines.extend(_made_by_lines(made))
            caps = cast(Mapping[str, Mapping[str, int]], explored.get("firingCaps", {}))
            for name, cap in caps.items():
                limit, stopped = cap["limit"], cap["stopped"]
                lines.append(
                    f"firing cap: [{name}] fires at most {limit} "
                    f"time{'s' if limit != 1 else ''} on a path (stopped it in "
                    f"{stopped} marking{'s' if stopped != 1 else ''}); results "
                    "hold only within the caps"
                )
            starts = explored.get("starts")
            if starts:
                lines.append(
                    f"starts: the instance starts {starts} times, with the same "
                    "keys; a final marking counts once per start"
                )
            producers = explored.get("readOnlyProducers")
            if producers:
                names = ", ".join(f"[{name}]" for name in producers)
                lines.append(
                    f"likely cause: {names} reads but consumes nothing, so it "
                    "can fire again and again (lint rule read-only-producer)"
                )
        lines.append("")
        lines.append(f"result: {self.status.upper()}")
        return "\n".join(lines) + "\n"


def _step_label(step: Mapping[str, Any]) -> str:
    kind = step["kind"]
    if "transition" in step:
        name = f"[{step['transition']}]"
        return f"record change by {name}" if kind == "record" else f"firing {name}"
    place = f"({step['place']})"
    return {
        "arrival": f"arrival in {place}",
        "update": f"update of {place}",
        "record": f"record change of {place}",
        "advance": f"clock advance of {place}",
    }[kind]


def _made_by_lines(made: Mapping[str, Any]) -> list[str]:
    """What made the markings of a capped run, as the text report says it
    (proofs.md, What made the markings)."""

    def number(value: int) -> str:
        return f"{value:,}".replace(",", " ")

    steps = cast(list[Mapping[str, Any]], made["steps"])
    rest = cast(Mapping[str, Any] | None, made.get("rest"))
    rows = [(step["share"], step["count"], _step_label(step)) for step in steps]
    if rest is not None:
        rows.append(
            (
                rest["share"],
                rest["count"],
                f"everything else ({rest['steps']} kinds of step)",
            )
        )
    width = max((len(number(count)) for _, count, _ in rows), default=0)
    lines = ["what made the markings: the steps that first reached them"]
    for share, count, label in rows:
        lines.append(f"  {round(share * 100):>3} %  {number(count):>{width}}  {label}")
    places = cast(list[Mapping[str, Any]], made["places"])
    if places:
        lines.append(
            "places that multiply the markings: how many become one when the "
            "place is ignored"
        )
        for place in places:
            factor = "×" + format(place["factor"], ".1f")
            lines.append(f"  {factor:>5}  ({place['place']})")
    return lines


def _finding_lines(finding: Finding) -> list[str]:
    label = "intended wait" if finding.kind == "wait" else finding.kind
    lines = [f"    - {label}: {finding.summary}"]
    if finding.path and not finding.play:
        lines.append("        path:")
        for move in finding.path:
            lines.append(f"          {move.text()}")
        if finding.cycle:
            lines.append("        then forever:")
            for move in finding.cycle:
                lines.append(f"          {move.text()}")
    if finding.play:
        lines.append(f"        counterexample: {finding.play}")
    return lines
