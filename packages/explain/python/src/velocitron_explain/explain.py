"""Deterministically render a validated core Petri net for people.

This module deliberately consumes only :class:`velocitron_engine.Net` data.  It
neither loads source documents nor resolves handlers or follows composition
wires.  It evaluates CEL only when asked which steps can happen from a
marking, and then through the engine's own enablement explanation.
The engine package requires an injected CEL adapter, so a marking
explanation passes :func:`velocitron_cel.get_default_adapter`.

``velocitron_explain`` re-exports :func:`explain_net`. This package does not
import ``velocitron``.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from velocitron_cel import get_default_adapter
from velocitron_engine import (
    Arc,
    ConsumePattern,
    EnablementReason,
    Engine,
    HandlerRegistry,
    Marking,
    Net,
    Place,
    Transition,
)

__all__ = ["explain_net"]


_PRESENTATION_ANNOTATION = "petrinet.dsl/v1"


def explain_net(
    net: Net,
    *,
    format: Literal["markdown", "text"] = "markdown",
    level: Literal["practitioner", "newcomer"] = "practitioner",
    marking: Marking | None = None,
    marking_label: str = "the given marking",
) -> str:
    """Return a deterministic, human-readable account of a validated ``net``.

    The renderer is intentionally descriptive rather than executable: handler
    references and CEL declarations are quoted as opaque declarations, and no
    behavior is inferred from names, prose, or annotations.  ``format`` is
    either ``"markdown"`` or ``"text"``; ``level`` is ``"practitioner"`` or
    ``"newcomer"``.  The returned document always has exactly one final LF.

    Args:
        net: A validated core :class:`~velocitron_engine.Net`.
        format: Select paragraph-led Markdown or its plain-text equivalent.
        level: Include the single introductory how-to-read section for newcomers.
        marking: Add a section that says, for each transition, whether it
            can happen from this marking or why it waits. No handler runs,
            so a named guard always holds its transition back.
        marking_label: How the section heading names ``marking``.

    Raises:
        ValueError: If ``format`` or ``level`` is not a supported value.
    """
    if format not in ("markdown", "text"):
        raise ValueError('format must be "markdown" or "text"')
    if level not in ("practitioner", "newcomer"):
        raise ValueError('level must be "practitioner" or "newcomer"')

    renderer = _MarkdownRenderer() if format == "markdown" else _TextRenderer()
    return renderer.render(
        net,
        include_how_to_read=level == "newcomer",
        marking=marking,
        marking_label=marking_label,
    )


class _Renderer:
    """Shared paragraph-led document construction independent of syntax."""

    def render(
        self,
        net: Net,
        *,
        include_how_to_read: bool,
        marking: Marking | None = None,
        marking_label: str = "the given marking",
    ) -> str:
        """Render ``net`` in declaration order without interpreting declarations."""
        places_by_name = {place.name: place for place in net.places}
        adjacent_places = {
            endpoint
            for arc in net.arcs
            for endpoint in (arc.from_place, arc.to_place)
            if endpoint is not None
        }
        lines: list[str] = [
            self.title(f"Net: {_quote(net.name)}"),
            "",
            self._overview(net),
        ]
        if include_how_to_read:
            lines.extend(["", self.heading("How to read"), self._how_to_read()])
        lines.extend(self._initial_marking(net))
        lines.extend(self._transitions(net.transitions, net.arcs, places_by_name))
        lines.extend(self._standalone_places(net.places, adjacent_places))
        if marking is not None:
            lines.extend(self._enablement(net, marking, marking_label))
        lines.extend(
            [
                "",
                self.heading("Faithfulness note"),
                self._faithfulness_note(enablement=marking is not None),
            ]
        )
        return "\n".join(lines).rstrip("\n") + "\n"

    def _enablement(self, net: Net, marking: Marking, label: str) -> list[str]:
        engine = Engine(HandlerRegistry(), cel_adapter=get_default_adapter())
        lines = ["", self.heading(f"What can happen from {label}")]
        for transition in net.transitions:
            explanation = engine.explain_enablement(net, marking, transition.name)
            if explanation.enabled:
                lines.append(f"- [{transition.name}] can happen.")
                continue
            reasons = explanation.reasons
            if not reasons:
                lines.append(
                    f"- [{transition.name}] waits: no choice of its input tokens "
                    "fits together."
                )
                continue
            first, *rest = (_plain_reason(net, reason) for reason in reasons)
            lines.append(f"- [{transition.name}] waits: {first}")
            lines.extend(f"  - also: {text}" for text in rest)
            for reason in reasons:
                lines.extend(f"  - {detail}" for detail in reason.details)
        return lines

    def title(self, text: str) -> str:
        """Return the document title line."""
        raise NotImplementedError

    def heading(self, text: str) -> str:
        """Return a top-level document section heading."""
        raise NotImplementedError

    def transition_heading(self, name: str) -> str:
        """Return the label introducing one transition's prose paragraph."""
        raise NotImplementedError

    def _overview(self, net: Net) -> str:
        sentences = [
            f"This net declares {len(net.places)} places, {len(net.transitions)} transitions, "
            f"and {len(net.arcs)} arcs."
        ]
        if net.description is not None:
            sentences.append(f"It declares description {_quote(net.description)}.")
        annotations = _core_annotations(net.annotations)
        if annotations is not None:
            sentences.append(f"It declares opaque annotations {_json(annotations)}.")
        return " ".join(sentences)

    def _how_to_read(self) -> str:
        return (
            "Places hold colored tokens. Input arcs state what must be present before a "
            "transition can be considered: consume arcs remove matching tokens, read arcs "
            "preserve them while binding them, and inhibit arcs require their absence. Output "
            "templates declare routing after the transition, rather than promising handler "
            "behavior. A port is a place facet rather than a wire, and capacity is a "
            "verification bound rather than an engine gate. Handler references, CEL, "
            "descriptions, and annotations remain quoted opaque declarations here."
        )

    def _initial_marking(self, net: Net) -> list[str]:
        marking = net.initial_marking
        if marking is None:
            return []

        lines = ["", self.heading("Initial marking")]
        names = [place.name for place in net.places if place.name in marking]
        if not names:
            lines.append("The declared initial marking is empty.")
            return lines

        for name in names:
            tokens = marking[name]
            if not tokens:
                lines.append(f"Place {_quote(name)} has no initial tokens.")
                continue
            token_text = "; ".join(
                f"token type {_quote(token.type)} with data {_json(token.data)}"
                for token in tokens
            )
            lines.append(f"Place {_quote(name)} initially contains {token_text}.")
        return lines

    def _transitions(
        self,
        transitions: list[Transition],
        arcs: list[Arc],
        places_by_name: dict[str, Place],
    ) -> list[str]:
        lines = ["", self.heading("Transition flow")]
        if not transitions:
            lines.append("No transitions are declared.")
            return lines

        for transition in transitions:
            inputs = [arc for arc in arcs if arc.to_transition == transition.name]
            outputs = [arc for arc in arcs if arc.from_transition == transition.name]
            lines.extend(
                [
                    "",
                    self.transition_heading(transition.name),
                    self._transition_paragraph(
                        transition, inputs, outputs, places_by_name
                    ),
                ]
            )
        return lines

    def _transition_paragraph(
        self,
        transition: Transition,
        inputs: list[Arc],
        outputs: list[Arc],
        places_by_name: dict[str, Place],
    ) -> str:
        sentences = (
            [
                f"This transition declares opaque handler reference "
                f"{_quote(transition.handler)}."
            ]
            if transition.handler is not None
            else ["No behavior handler is bound to this transition."]
        )
        if not inputs and not outputs:
            sentences.append("It has no immediate input or output arcs.")
        elif not inputs:
            sentences.append(
                "It is a source transition because it has no immediate input arcs."
            )
        elif not outputs:
            sentences.append(
                "It is a sink transition because it has no immediate output arcs."
            )

        if transition.guard is not None:
            sentences.append(f"It declares opaque guard {_quote(transition.guard)}.")
        if transition.priority is not None:
            sentences.append(f"It declares priority {transition.priority}.")
        if transition.timer is not None:
            timer = transition.timer
            bindings = (
                f" and bindings {_json(timer.bind)}" if timer.bind is not None else ""
            )
            sentences.append(
                f"It declares a timer using clock {_quote(timer.clock)}, opaque CEL "
                f"{_quote(timer.cel)}{bindings}."
            )
        if transition.description is not None:
            sentences.append(
                f"It declares description {_quote(transition.description)}."
            )
        annotations = _core_annotations(transition.annotations)
        if annotations is not None:
            sentences.append(f"It declares opaque annotations {_json(annotations)}.")

        if inputs:
            input_clauses = [
                self._input_clause(arc, places_by_name[arc.from_place])
                for arc in inputs
                # Validated core nets always provide input endpoints and contracts.
                if arc.from_place is not None and arc.consume is not None
            ]
            sentences.append("Its inputs are " + "; ".join(input_clauses) + ".")
        if outputs:
            output_clauses = [
                self._output_clause(arc, places_by_name[arc.to_place])
                for arc in outputs
                # Validated core nets always provide output endpoints and templates.
                if arc.to_place is not None and arc.produce is not None
            ]
            sentences.append(
                "Its declared postcondition routes output through "
                + "; ".join(output_clauses)
                + "."
            )
        return " ".join(sentences)

    def _input_clause(self, arc: Arc, place: Place) -> str:
        assert arc.consume is not None
        pattern = arc.consume
        source = self._place_phrase(place)
        predicate = self._predicate_clause(pattern)
        if pattern.mode != "inhibit" and pattern.correlate is not None:
            predicate += (
                f", joined to the candidate binding by opaque correlate CEL "
                f"{_quote(pattern.correlate)}"
            )
        arc_metadata = self._arc_metadata_clause(arc)
        if pattern.mode == "consume":
            clause = (
                f"{source}, consuming {_token_count(pattern.weight)} of type "
                f"{_quote(pattern.type)}{predicate}"
            )
        elif pattern.mode == "read":
            clause = (
                f"{source}, reading and binding {_token_count(pattern.weight)} of type "
                f"{_quote(pattern.type)}{predicate} while preserving those tokens"
            )
        elif pattern.correlate is None:
            clause = (
                f"{source}, an inhibit check requiring no matching token of type "
                f"{_quote(pattern.type)}{predicate} and removing none"
            )
        else:
            clause = (
                f"{source}, a correlated inhibit check requiring, for each candidate binding, "
                f"no matching token of type {_quote(pattern.type)}{predicate} satisfying "
                f"opaque correlate CEL {_quote(pattern.correlate)}, and removing none"
            )
        return clause + arc_metadata

    def _output_clause(self, arc: Arc, place: Place) -> str:
        assert arc.produce is not None
        template = arc.produce
        if template.data is not None:
            data = f", with literal data {_json(template.data)}"
        elif template.cel is not None:
            # ADR 0023 computed produce fallback: an opaque CEL expression
            # over the firing's consumed binding, applied only when the
            # handler leaves this destination/type pair uncovered.
            data = (
                f", with data computed by opaque CEL {_quote(template.cel)} "
                "over the consumed binding when the handler leaves this "
                "destination/type pair uncovered"
            )
        else:
            data = ""
        return (
            f"{self._place_phrase(place)}: template token type {_quote(template.type)} "
            f"declares destination {_quote(template.destination)}{data}"
            f"{self._arc_metadata_clause(arc)}"
        )

    def _predicate_clause(self, pattern: ConsumePattern) -> str:
        predicate = pattern.predicate
        if predicate is None:
            return ""
        if predicate.cel is not None:
            return f" whose opaque CEL predicate is {_quote(predicate.cel)}"
        assert predicate.handler is not None
        return f" whose opaque predicate handler is {_quote(predicate.handler)}"

    def _arc_metadata_clause(self, arc: Arc) -> str:
        clauses: list[str] = []
        if arc.description is not None:
            clauses.append(f"description {_quote(arc.description)}")
        annotations = _core_annotations(arc.annotations)
        if annotations is not None:
            clauses.append(f"opaque annotations {_json(annotations)}")
        return f" (arc declares {', '.join(clauses)})" if clauses else ""

    def _standalone_places(
        self, places: list[Place], adjacent_places: set[str]
    ) -> list[str]:
        standalone_places = [
            place for place in places if place.name not in adjacent_places
        ]
        if not standalone_places:
            return []
        return [
            "",
            self.heading("Standalone places"),
            *(self._standalone_place_paragraph(place) for place in standalone_places),
        ]

    def _standalone_place_paragraph(self, place: Place) -> str:
        return f"{self._place_phrase(place, leading=True)} has no adjacent transition."

    def _place_phrase(self, place: Place, *, leading: bool = False) -> str:
        color_text = (
            "accepts colors " + ", ".join(_quote(color) for color in place.accepts)
            if place.accepts
            else "accepts no colors"
        )
        facets = [color_text]
        if place.port is not None:
            article = "an" if place.port.direction[0] in "aeiou" else "a"
            facets.append(
                f"has {article} {_quote(place.port.direction)} port accepting "
                f"{_quote(place.port.type)}"
            )
        if place.capacity_per_color_key is not None:
            capacity = place.capacity_per_color_key
            keys = ", ".join(_quote(key) for key in capacity.keys)
            token_word = "token" if capacity.max == 1 else "tokens"
            facets.append(
                f"has capacity {capacity.max} {token_word} per distinct value of {keys}"
            )
        if place.description is not None:
            facets.append(f"declares description {_quote(place.description)}")
        annotations = _core_annotations(place.annotations)
        if annotations is not None:
            facets.append(f"declares opaque annotations {_json(annotations)}")
        label = (
            f"Place {_quote(place.name)}" if leading else f"place {_quote(place.name)}"
        )
        return f"{label} ({'; '.join(facets)})"

    def _faithfulness_note(self, *, enablement: bool = False) -> str:
        if enablement:
            return (
                "This account reports only validated core-Net declarations. It does not "
                "infer behavior from names, expressions, descriptions, or annotations, and "
                "it does not resolve handlers, load source, or follow composition. Only the "
                "section on what can happen evaluates CEL: it asks the engine, which "
                "evaluates predicates, correlates and timers on that marking. No handler "
                "runs there, so a named guard or predicate always holds its transition back."
            )
        return (
            "This account reports only validated core-Net declarations. It does not infer "
            "behavior from names, expressions, descriptions, or annotations, and it does not "
            "resolve handlers, evaluate CEL, load source, or follow composition."
        )


class _MarkdownRenderer(_Renderer):
    """Render the paragraph-led document with Markdown headings."""

    def title(self, text: str) -> str:
        """Return a level-one Markdown heading."""
        return f"# {text}"

    def heading(self, text: str) -> str:
        """Return a level-two Markdown heading."""
        return f"## {text}"

    def transition_heading(self, name: str) -> str:
        """Return a level-three heading for a transition."""
        return f"### Transition {_quote(name)}"


class _TextRenderer(_Renderer):
    """Render the paragraph-led document with uppercase plain-text labels."""

    def title(self, text: str) -> str:
        """Return an uppercase plain-text document title without mutating declarations."""
        label, separator, declaration = text.partition(": ")
        return f"{label.upper()}{separator}{declaration}"

    def heading(self, text: str) -> str:
        """Return an uppercase plain-text section heading."""
        return text.upper()

    def transition_heading(self, name: str) -> str:
        """Return an uppercase plain-text transition label."""
        return f"TRANSITION {_quote(name)}"


def _plain_reason(net: Net, reason: EnablementReason) -> str:
    """Say a short input place in words; other gates keep the engine's line."""
    if reason.gate != "arc-short" or reason.arc is None:
        return reason.message
    consume = net.arcs[reason.arc].consume
    assert consume is not None
    place, color, weight = reason.place, consume.type, consume.weight
    wanted = f"a {color} token" if weight == 1 else f"{weight} {color} tokens"
    if not reason.tokens:
        return f"({place}) is empty; it needs {wanted} there."
    held = len(reason.tokens)
    noun = "token" if held == 1 else "tokens"
    enough = "none" if weight == 1 else f"fewer than {weight}"
    return f"({place}) holds {held} {noun}, but {enough} that this step accepts:"


def _token_count(weight: int) -> str:
    """Return a default-implicit or explicit non-default arc-weight phrase."""
    if weight == 1:
        return "a matching token"
    return f"{weight} matching tokens"


def _core_annotations(annotations: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop DSL presentation metadata, which is outside core-Net explanation scope."""
    if annotations is None:
        return None
    core_annotations = {
        key: value
        for key, value in annotations.items()
        if key != _PRESENTATION_ANNOTATION
    }
    return core_annotations or None


def _json(value: Any) -> str:
    """Canonically serialize a JSON value with Unicode preserved."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _quote(value: str) -> str:
    """Canonically quote a declaration string as a JSON string literal."""
    return _json(value)
