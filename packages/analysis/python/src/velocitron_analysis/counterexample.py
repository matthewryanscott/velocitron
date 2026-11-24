"""Write a witness or a counterexample as a ``.play`` file.

Each file plays against the net by ``velocitron play check``: an
arrival is an ``inject``, an update an ``update``, a clock move an
``update`` (the machine form of the authoring word ``advance``, immune to
the statement's maturation) and a
firing a ``fire`` with ``->`` outputs for the templates a handler fills and
``with`` clauses where a place holds more than one token. The last steps
are ``expect`` lines that state what the finding says, so the play
checker confirms the finding and ``velocitron play walk`` draws it.

References: spec/proofs.md; spec/play-language.md; ADR 0036.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from velocitron_engine import Marking, Net, Token

from .firing import Firing
from .report import Finding, Move, Proof, ProofReport


def _json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False)


def _token(token: Token) -> str:
    return f"{token.type} {_json(token.data)}"


def _ident(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]+", "_", text).strip("_")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"n_{cleaned}"
    return cleaned


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()


def _sentence(text: str) -> str:
    text = text[:1].upper() + text[1:]
    return text if text.endswith(".") else text + "."


def _prose(text: str) -> list[str]:
    return [f"/// {line}" if line else "///" for line in text.splitlines()]


def _expect_places(
    marking: Mapping[str, Sequence[Token]], places: Sequence[str]
) -> list[str]:
    conditions: list[str] = []
    for place in places:
        tokens = list(marking.get(place, ()))
        if tokens:
            conditions.append(f"({place}) == " + ", ".join(_token(t) for t in tokens))
        else:
            conditions.append(f"({place}) empty")
    return conditions


class PlayWriter:
    def __init__(
        self, net: Net, firing: Firing, net_file: Path, directory: Path
    ) -> None:
        self.net = net
        self.firing = firing
        self.net_file = net_file
        self.directory = directory

    def _header(self, name: str, title: str) -> list[str]:
        reference = os.path.relpath(self.net_file.resolve(), self.directory.resolve())
        return [
            f"play {_ident(name)} {_json(title)}",
            f"net {_json(Path(reference).as_posix())}",
        ]

    def _instance(self) -> list[str]:
        """The ``instance`` line a kept record's start is built from."""
        model = self.firing.model
        if not any(record.reads_instance for record in model.kept.values()):
            return []
        token = Token(model.roles.instance_color, model.instance_data())
        return [f"instance {_token(token)}"]

    def _step(self, move: Move, marking: Marking) -> tuple[str, Marking]:
        if move.kind == "fire":
            assert move.transition is not None
            parts = [f"fire [{move.transition}]"]
            for place, tokens in move.binding:
                if len(marking.get(place, ())) > len(tokens):
                    for token in tokens:
                        parts.append(f"with ({place}) {_json(token.data)}")
            binding = {place: list(tokens) for place, tokens in move.binding}
            consumed = [
                token
                for tokens in self.firing.consumed(
                    marking, move.transition, binding
                ).values()
                for token in tokens
            ]
            for place, tokens in move.outputs:
                carried = [t for t in consumed if t.type == tokens[0].type]
                if len(tokens) == 1 and len(carried) == 1 and carried[0] == tokens[0]:
                    continue  # the play's carry rule gives this output
                parts.append(f"-> ({place}) " + ", ".join(_token(t) for t in tokens))
            fired = self.firing.fire(
                marking,
                move.transition,
                {place: list(tokens) for place, tokens in move.binding},
                move.outputs,
            )
            return " ".join(parts), fired.marking
        assert move.place is not None and move.token is not None
        token = move.token
        if move.kind == "inject":
            after = marking.set(move.place, [*marking.get(move.place, ()), token])
            return f"inject ({move.place}) <- {_token(token)}", after
        # Machine artifacts only: clock moves are written as ``update``
        # statements (replace semantics) rather than ``advance`` so the
        # written play is immune to the advance statement's maturation and
        # replays the walk's move order exactly.
        after = marking.set(move.place, [token])
        if move.kind == "advance" and not marking.get(move.place):
            return f"inject ({move.place}) <- {_token(token)}", after
        return f"update ({move.place}) <- {_token(token)}", after

    def soundness(
        self,
        proof: Proof,
        finding: Finding,
        instance: Sequence[str],
        final: Sequence[str],
    ) -> str:
        name = f"{self.net.name}_{_slug(proof.subject)}"
        lines = self._header(name, f"{proof.subject}: {finding.kind}")
        lines += self._instance()
        lines += ["marking initial", ""]
        lines += _prose(f"**{proof.status.upper()}** — {proof.statement}")
        lines += ["///"] + _prose(_sentence(finding.summary)) + [""]
        marking = self.firing.model.initial_marking()
        for move in finding.path:
            line, marking = self._step(move, marking)
            lines.append(line)
        if finding.kind == "livelock":
            held = [p for p in instance if marking.get(p)]
            before = _expect_places(marking, held)
            if before:
                lines.append("expect " + ", ".join(before))
            lines.append("")
            lines += _prose(
                "From here the net goes round this loop, and the marking comes back:"
            )
            for move in finding.cycle:
                line, marking = self._step(move, marking)
                lines.append(line)
            if before:
                lines.append("expect " + ", ".join(before))
        elif finding.kind in ("deadlock", "vanished"):
            lines.append("")
            lines += _prose("Nothing is enabled, and no final marking is reached.")
            conditions = ["quiescent"] + [
                f"({p}) count {len(marking.get(p, ()))}"
                if marking.get(p)
                else f"({p}) empty"
                for p in final
            ]
            lines.append("expect " + ", ".join(conditions))
        elif finding.kind == "improper":
            lines.append("")
            lines += _prose(
                "A final marking is reached, and the instance still holds tokens elsewhere."
            )
            marked = [p for p in final if marking.get(p)]
            left = [p for p in instance if marking.get(p)]
            conditions = [
                f"({p}) count {len(marking.get(p, ()))}" for p in marked + left
            ]
            lines.append("expect " + ", ".join(conditions))
        return "\n".join(lines) + "\n"

    def choice(self, proof: Proof, finding: Finding) -> str:
        place = proof.details["place"]
        names: list[str] = list(proof.details["transitions"])
        name = f"{self.net.name}_choice_{place}_{finding.kind}"
        lines = self._header(name, f"{proof.subject}: {finding.kind}")
        lines += ["marking none", ""]
        lines += _prose(f"**{proof.status.upper()}** — {proof.statement}")
        lines += ["///"] + _prose(_sentence(finding.summary)) + [""]
        witness = finding.witness or {}
        kept = self.firing.model.kept
        for target in sorted(witness, key=lambda p: (p == place, p)):
            tokens = [Token(t["type"], t["data"]) for t in witness[target]]
            # A story keeps a record whose start needs no instance from its
            # first step, so the witness's value replaces it.
            verb = (
                "update"
                if target in kept
                and not kept[target].reads_instance
                and len(tokens) == 1
                else "inject"
            )
            lines.append(
                f"{verb} ({target}) <- " + ", ".join(_token(t) for t in tokens)
            )
        if finding.kind in ("gap", "waived-gap"):
            lines.append("expect not enabled " + " ".join(f"[{n}]" for n in names))
        else:
            lines.append(
                "expect enabled " + " ".join(f"[{n}]" for n in finding.enabled)
            )
            rest = [n for n in names if n not in finding.enabled]
            if rest:
                lines.append("expect not enabled " + " ".join(f"[{n}]" for n in rest))
        return "\n".join(lines) + "\n"


def write_counterexamples(
    report: ProofReport,
    net: Net,
    firing: Firing,
    net_file: Path,
    directory: Path,
    *,
    instance: Sequence[str],
    final: Sequence[str],
    facts: Sequence[str] = ("choice", "soundness"),
) -> ProofReport:
    """Write one ``.play`` per witness and counterexample of ``facts``
    into ``directory``; return the report with each finding's file name set.

    A refinement's findings play against the refining net, not ``net``, so
    the caller writes them with that net and ``facts=("refinement",)``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    writer = PlayWriter(net, firing, net_file, directory)
    proofs: list[Proof] = []
    used: dict[str, int] = {}
    for proof in report.proofs:
        if proof.fact not in facts:
            proofs.append(proof)
            continue
        findings: list[Finding] = []
        for finding in proof.findings:
            text: str | None = None
            if proof.fact in ("soundness", "refinement") and finding.path:
                text = writer.soundness(proof, finding, instance, final)
            elif (
                proof.fact == "choice"
                and finding.witness
                and finding.kind in ("gap", "overlap")
            ):
                text = writer.choice(proof, finding)
            if text is None:
                findings.append(finding)
                continue
            stem = f"{_slug(net.name)}.{_slug(proof.subject.split(':')[0])}"
            if proof.fact == "choice":
                stem += f".{finding.kind}"
            used[stem] = used.get(stem, 0) + 1
            filename = f"{stem}-{used[stem]}.play"
            (directory / filename).write_text(text, encoding="utf-8")
            findings.append(replace(finding, play=str(directory / filename)))
        proofs.append(proof.with_findings(findings))
    return replace(report, proofs=tuple(proofs))
