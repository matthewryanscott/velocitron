"""Compile ``.petrinet`` text to canonical JSON and load it as a net.

Lowering is ``velocitron_dsl``. Resolution and the closing JSON parse live
in this package. Canonical ``.petrinet`` emission stays in ``velocitron_dsl``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from velocitron_dsl import (
    Diagnostic,
    PetrinetDslError,
    SourcePosition,
    SourceSpan,
    lower_petrinet_text,
)
from velocitron_engine import Net

from .parse import parse_net
from .resolve import SourceInput, resolve_contribution_ir

def _aggregation_error(message: str, span: Mapping[str, Any]) -> PetrinetDslError:
    start = cast(Mapping[str, int], span["start"])
    end = cast(Mapping[str, int], span["end"])
    return PetrinetDslError(
        Diagnostic(
            "PN200",
            message,
            SourceSpan(
                str(span["source"]),
                SourcePosition(start["byteOffset"], start["line"], start["column"]),
                SourcePosition(end["byteOffset"], end["line"], end["column"]),
            ),
        )
    )


def compile_petrinet_sources(
    sources: Sequence[SourceInput],
    *,
    net_loader: Callable[[str], Mapping[str, Any] | Path | str] | None = None,
    origin: Path | None = None,
    validate_ir: bool = True,
) -> dict[str, Any]:
    """Lower same-namespace sources in order, then resolve their aggregate once.

    ``validate_ir=False`` skips the Contribution IR schema check during
    resolution. For a valid source the compiled document is identical to
    the default; for an invalid one the failure moves from the schema
    diagnostic to a later resolution or net-validation error (see
    :func:`velocitron_petrinet.resolve_contribution_ir`). Intended for
    consumers that recompile trusted sources, such as a Pyodide primer app.
    """
    if not sources:
        raise ValueError("at least one SourceInput is required")
    if len(sources) == 1:
        source = sources[0]
        return resolve_contribution_ir(
            lower_petrinet_text(source.text, source.source_id),
            net_loader=net_loader,
            origin=origin,
            validate_ir=validate_ir,
        )

    seen_source_ids: set[str] = set()
    for source in sources:
        if source.source_id in seen_source_ids:
            position = {"byteOffset": 0, "line": 1, "column": 1}
            raise _aggregation_error(
                f"duplicate aggregate source id {source.source_id!r}",
                {
                    "source": source.source_id,
                    "start": position,
                    "end": position,
                },
            )
        seen_source_ids.add(source.source_id)

    lowered = [lower_petrinet_text(source.text, source.source_id) for source in sources]
    document_kind = lowered[0]["documentKind"]
    header_kind = (
        "document.net-header"
        if document_kind == "net"
        else "document.composition-header"
    )
    header_name_member = "name" if document_kind == "net" else "namespace"
    first_contributions = cast(list[dict[str, Any]], lowered[0]["contributions"])
    first_header = next(
        (
            contribution
            for contribution in first_contributions
            if contribution["kind"] == header_kind
        ),
        None,
    )
    header_name = (
        "unnamed" if first_header is None else first_header["value"][header_name_member]
    )

    aggregate_contributions: list[dict[str, Any]] = []
    for document in lowered:
        contributions = cast(list[dict[str, Any]], document["contributions"])
        position = {"byteOffset": 0, "line": 1, "column": 1}
        fallback_span: Mapping[str, Any] = {
            "source": cast(Mapping[str, str], document["document"])["id"],
            "start": position,
            "end": position,
        }
        if document["documentKind"] != document_kind:
            raise _aggregation_error(
                "aggregate sources must have the same document kind",
                cast(Mapping[str, Any], contributions[0]["span"])
                if contributions
                else fallback_span,
            )
        header = next(
            (
                contribution
                for contribution in contributions
                if contribution["kind"] == header_kind
            ),
            None,
        )
        document_name = (
            "unnamed" if header is None else header["value"][header_name_member]
        )
        if document_name != header_name:
            raise _aggregation_error(
                "aggregate sources must have the same decoded header name",
                cast(Mapping[str, Any], header["span"])
                if header is not None
                else (
                    cast(Mapping[str, Any], contributions[0]["span"])
                    if contributions
                    else fallback_span
                ),
            )
        for contribution in contributions:
            contribution["ordinal"] = len(aggregate_contributions)
            aggregate_contributions.append(contribution)

    aggregate = dict(lowered[0])
    aggregate["contributions"] = aggregate_contributions
    return resolve_contribution_ir(
        aggregate,
        source_ids=[source.source_id for source in sources],
        net_loader=net_loader,
        origin=origin,
        validate_ir=validate_ir,
    )


def compile_petrinet_text(
    text: str,
    source_name: str = "<memory>",
    *,
    net_loader: Callable[[str], Mapping[str, Any] | Path | str] | None = None,
    origin: Path | None = None,
    validate_ir: bool = True,
) -> dict[str, Any]:
    """Compile DSL text to canonical net- or composition-shaped core JSON.

    ``validate_ir=False`` skips the Contribution IR schema check during
    resolution. For a valid source the compiled document is byte-identical
    to the default; for an invalid one the failure surfaces later, at a
    resolution or net-validation error instead of the schema diagnostic.
    Intended for consumers that recompile trusted sources, such as a
    Pyodide primer app.
    """
    source_path = Path(source_name)
    source_id = source_path.name if source_path.is_absolute() else source_name
    return compile_petrinet_sources(
        [SourceInput(source_id, text)],
        net_loader=net_loader,
        origin=origin,
        validate_ir=validate_ir,
    )


def parse_petrinet_text(text: str, source_name: str = "<memory>") -> Net:
    """Compile DSL text then delegate all net semantics to :func:`parse_net`."""
    return parse_net(compile_petrinet_text(text, source_name))


def read_petrinet_text(path: Path | str) -> str:
    """Read UTF-8 DSL source without translating its accepted CRLF bytes."""
    with Path(path).open("r", encoding="utf-8", newline="") as source:
        return source.read()


def load_petrinet(path: Path | str) -> Net:
    """Read strict UTF-8 DSL text from a path and parse it into a validated Net."""
    source = Path(path)
    return parse_petrinet_text(read_petrinet_text(source), str(source))

