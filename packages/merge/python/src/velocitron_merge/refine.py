"""Refinement fit check for the composition merge.

This module is the source of truth for the fit check. Wire checks and
document parsing ship in ``velocitron_petrinet``. This module does not
import ``velocitron``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from .errors import NetValidationError
from .types import Net, Port, Refinement, Share, Wire

def find_port(net: Net, port_name: str) -> Port | None:
    """Locate a port facet by place name (ports are place facets)."""
    for place in net.places:
        if place.name == port_name and place.port is not None:
            return place.port
    return None


def validate_refinements(  # pyright: ignore[reportUnusedFunction]
    refinements: Iterable[Refinement],
    wires: Iterable[Wire],
    alias_to_net: Mapping[str, Net],
    shares: Iterable[Share] = (),
) -> None:
    """Check that each refining net fits the transition it replaces.

    Every place the transition consumes from or reads must be wired (directly
    or through a fused class) to an input port of the refining net with the
    arc's color, and every place it produces into must be wired from an output
    port of the refining net with that color. Inhibit arcs and timers are
    rejected: no port direction carries a test for absence or a clock.
    """
    neighbors: dict[str, set[str]] = {}
    for wire in wires:
        source = f"{wire.from_net}.{wire.from_port}"
        sink = f"{wire.to_net}.{wire.to_port}"
        neighbors.setdefault(source, set()).add(sink)
        neighbors.setdefault(sink, set()).add(source)
    for share in shares:
        names = [f"{net}.{place}" for net, place in share.members]
        for name in names:
            neighbors.setdefault(name, set()).update(names)

    def fused_with(qualified_place: str) -> set[str]:
        members = {qualified_place}
        pending = [qualified_place]
        while pending:
            for neighbor in neighbors.get(pending.pop(), ()):
                if neighbor not in members:
                    members.add(neighbor)
                    pending.append(neighbor)
        return members

    refined_by: dict[tuple[str, str], str] = {}
    for refinement in refinements:
        net_alias, name, by = refinement.net, refinement.transition, refinement.by
        prefix = f"refine {net_alias}.[{name}] by {by}: "
        for alias in (net_alias, by):
            if alias not in alias_to_net:
                raise NetValidationError(f"{prefix}unknown alias {alias}")
        if by == net_alias:
            raise NetValidationError(f"{prefix}a net cannot refine its own transition")
        earlier = refined_by.get((net_alias, name))
        if earlier is not None:
            raise NetValidationError(
                f"{prefix}{net_alias}.[{name}] is already refined by {earlier}"
            )
        refined_by[(net_alias, name)] = by
        net = alias_to_net[net_alias]
        transition = next((t for t in net.transitions if t.name == name), None)
        if transition is None:
            raise NetValidationError(
                f"{prefix}net {net_alias} has no transition [{name}]"
            )
        if transition.timer is not None:
            raise NetValidationError(
                f"{prefix}[{name}] has a timer; a refined transition may only "
                "consume, read and produce"
            )
        subnet = alias_to_net[by]
        for arc in net.arcs:
            if arc.to_transition == name and arc.consume is not None:
                place, color = arc.from_place, arc.consume.type
                if arc.consume.mode == "inhibit":
                    raise NetValidationError(
                        f"{prefix}[{name}] has an inhibit arc from ({place}); a "
                        "refined transition may only consume, read and produce"
                    )
                direction, flow = "input", f"takes {color} from ({place})"
                link = "to an input port of"
            elif arc.from_transition == name and arc.produce is not None:
                place, color = arc.to_place, arc.produce.type
                direction, flow = "output", f"gives {color} to ({place})"
                link = "from an output port of"
            else:
                continue
            port_types: set[str] = set()
            for member in fused_with(f"{net_alias}.{place}"):
                port = (
                    find_port(subnet, member[len(by) + 1 :])
                    if member.startswith(f"{by}.")
                    else None
                )
                if port is not None and port.direction == direction:
                    port_types.add(port.type)
            if color in port_types:
                continue
            if not port_types:
                raise NetValidationError(
                    f"{prefix}[{name}] {flow}, but ({place}) is not wired {link} {by}"
                )
            raise NetValidationError(
                f"{prefix}[{name}] {flow}, but the {direction} ports of {by} "
                f"wired to it carry {', '.join(sorted(port_types))}"
            )
