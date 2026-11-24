"""Soundness of one lifecycle instance, by explicit state exploration.

The explorer builds every marking that one instance can reach under the
environment model, as a graph with four kinds of move:

- **net moves**: a firing (every binding, every output the domains allow;
  under the priority policy only the highest-priority enabled transitions),
  or a clock advance to a later time slot or to a time a timer on it declares
  it matures at. Time always passes, and an enabled
  transition eventually fires (the progress assumption).
- **arrivals**: the environment puts a token into an open place: the token
  that starts the instance (once, or as often as the domains file's
  ``starts`` says, ADR 0052), a fact or a resource (at most once per place
  unless the domains file allows more).
- **updates**: the environment replaces a read-only fact with another value
  (at most once per place unless the domains file allows more).
- a **firing cap** from the domains file disables a transition on a path
  once it fired that many times there, so a loop is explored for a bounded
  number of turns. The counts are part of the state. A marking where a cap
  stopped an enabled transition is **cut**: what lies past it is not
  explored, so it is neither a stop nor a proof of anything (ADR 0050).
- **record changes**: an update of a record (a place that lives in a
  ``record`` lifeline), any number of times, or a **record move**: a firing
  whose input and output places are all records, such as a person flipping
  a switch. They are the outside world's moves, not the net's.

Ticks and record changes wait until something can use them (ADR 0055): a
clock ticks only when a timer on it could fire at some clock value still to
come, and a record changes only when a transition that uses it has its other
inputs, or when the net has no move of its own. Arrivals wait on the same
terms, and the environment tries one token per class of tokens that the
steps reading the place cannot tell apart (ADR 0061); a copy into a side
output tells no tokens apart (ADR 0065). A place the net only counts keeps
as many equal tokens as its readers count (ADR 0062).

Three facts are checked on that graph (van der Aalst's workflow-net
soundness, for one instance):

- **option to complete**: from every reachable marking, net moves alone can
  reach a final marking, or else the net stops (no net move) and an arrival
  or a record change lets it go on to complete. A loop of net moves that
  never completes unless the environment acts is a refutation (a livelock).
- **proper completion**: when a final place is marked, no other place of the
  instance holds a token.
- **no dead transitions**: every transition fires somewhere.

References: spec/proofs.md; ADR 0036; ADR 0050; ADR 0052; ADR 0055; ADR 0061;
ADR 0062; ADR 0065.
"""

from __future__ import annotations

import json
import random
from array import array
from collections import Counter, deque
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, cast

from velocitron_engine import (
    Arc,
    FiringReservation,
    Marking,
    Net,
    Token,
    domain_violation,
)

from . import celscan
from .analysis import ENVIRONMENT, INSTANCE, NetModel
from .celscan import Opaque
from .firing import Firing, MarkingKeys, token_key
from .progress import Progress
from .report import Finding, Move, Proof, token_text

NET, ARRIVAL, UPDATE, RECORD = "net", "arrival", "update", "record"


@dataclass(frozen=True)
class Environment:
    """How often the environment may write each open place, and how often a
    capped transition may fire on one path."""

    injections: Mapping[str, int] = field(default_factory=dict[str, int])
    updates: Mapping[str, int] = field(default_factory=dict[str, int])
    firings: Mapping[str, int] = field(default_factory=dict[str, int])
    starts: int = 1

    def assumptions(self) -> tuple[str, ...]:
        """The firing caps, as sentences a proof that relies on them states."""
        return tuple(
            f"[{name}] fires at most {limit} time{'s' if limit != 1 else ''} on a path"
            for name, limit in sorted(self.firings.items())
        )

    def start_assumptions(self) -> tuple[str, ...]:
        """The repeated starts, as a sentence every soundness result states,
        a refutation too: its path may need the later starts (ADR 0052)."""
        if self.starts == 1:
            return ()
        return (
            f"the instance starts {self.starts} times, with the same keys each time",
        )


@dataclass
class _State:
    marking: Marking
    used: tuple[tuple[str, int], ...]
    edges: list[tuple[int, int, str]] = field(default_factory=list)
    expanded: bool = False
    final: bool = False
    cut: bool = False


def _at(data: Any, path: Sequence[Any]) -> Any:
    """The value at ``path`` inside a token's data.

    A step that is not a map yields ``None``.
    """
    value: Any = data
    for part in path:
        if not isinstance(value, dict):
            return None
        value = cast(dict[Any, Any], value).get(part)
    return value


class Explorer:
    def __init__(
        self,
        net: Net,
        model: NetModel,
        firing: Firing,
        *,
        environment: Environment,
        max_states: int,
        postpone: bool = True,
        wait_arrivals: bool = False,
        group_tokens: bool = True,
        saturate: bool = True,
        progress: Progress | None = None,
    ) -> None:
        self.net = net
        self.model = model
        self.roles = model.roles
        self.firing = firing
        self.environment = environment
        self.max_states = max_states
        self.progress = progress
        self.postpone = postpone
        self.wait_arrivals = wait_arrivals
        self.group_tokens = group_tokens
        views = _views(net, model) if group_tokens or saturate else {}
        self._views = views if group_tokens else {}
        self._counted = self._counted_places(views) if saturate else {}
        self.place_names = [place.name for place in net.places]
        self._marking_keys = MarkingKeys(self.place_names, self._token_text)
        self.priority_mode = any(tr.priority is not None for tr in net.transitions)
        self.priority = {tr.name: tr.priority or 0 for tr in net.transitions}
        self.moves: list[Move] = []
        self._move_ids: dict[Any, int] = {}
        self.states: list[_State] = []
        self._ids: dict[Any, int] = {}
        self.parent: dict[int, tuple[int, int]] = {}
        self.capped = False
        self.deposit_errors: list[str] = []
        self.stopped: dict[str, int] = {}
        # Per timed transition, the maturities the exploration did not move
        # time to (a latch on a time the clock's values do not list).
        self.withheld: dict[str, set[int | float]] = {}
        self._withheld_states: set[int] = set()
        self._env_tokens: dict[str, list[Token]] = {}
        self._clock_values: dict[str, tuple[Any, ...]] = {}
        self._clock_field: dict[str, str] = {}
        self._consumers: dict[str, list[str]] = {}
        self._inputs: dict[str, set[str]] = {}
        self._outputs: dict[str, set[str]] = {}
        self._needs: dict[str, set[str]] = {}
        self._relevances: dict[
            Any, tuple[set[str], set[str], tuple[tuple[str, int], ...]]
        ] = {}
        self._token_texts: dict[int, tuple[Token, str]] = {}
        self._timer_checks: dict[Any, bool] = {}
        self._waiting_records: dict[frozenset[str], frozenset[str]] = {}
        self._waiting_places: dict[frozenset[str], frozenset[str]] = {}
        self._before_start: dict[Any, frozenset[str]] = {}
        self.held_moves: set[str] = set()
        for tr in net.transitions:
            self._needs[tr.name] = {
                a.from_place
                for a in model.inputs.get(tr.name, ())
                if a.consume is not None
                and a.consume.mode != "inhibit"
                and a.from_place
            }
            ins = {a.from_place for a in model.inputs.get(tr.name, ()) if a.from_place}
            if tr.timer is not None:
                ins.add(tr.timer.clock)
            self._inputs[tr.name] = ins
            self._outputs[tr.name] = {
                a.produce.destination
                for a in model.outputs.get(tr.name, ())
                if a.produce
            }
        records = self.roles.records
        self._record_moves = {
            name
            for name in self._inputs
            if self._inputs[name] | self._outputs[name]
            and self._inputs[name] | self._outputs[name] <= records
        }
        self._timed = {
            clock: [
                tr.name
                for tr in net.transitions
                if tr.timer is not None and tr.timer.clock == clock
            ]
            for clock in self.roles.clocks
        }
        self._record_users = self._users_of_records()
        self._place_users = self._users_of_open_places()
        self._prepare_environment()

    def _users_of_records(self) -> dict[frozenset[str], list[str]]:
        """Each group of records that record moves join, and the net's
        transitions that read or write a record of the group."""
        group = {record: {record} for record in self.roles.records}
        for name in self._record_moves:
            touched: set[str] = set()
            for record in self._inputs[name] | self._outputs[name]:
                touched |= group[record]
            for record in touched:
                group[record] = touched
        users: dict[frozenset[str], list[str]] = {}
        for members in {frozenset(g) for g in group.values()}:
            users[members] = [
                name
                for name in self._inputs
                if name not in self._record_moves
                and (self._inputs[name] | self._outputs[name]) & members
            ]
        return users

    def _users_of_open_places(self) -> dict[str, list[str]]:
        """Each open place that can wait for its arrival (ADR 0061), and its
        users: the transitions with an input arc from it (consume, read or
        inhibit, a timer's bind included) or an output arc into it."""
        roles = self.roles
        return {
            place: [
                name
                for name in self._inputs
                if place in self._inputs[name] | self._outputs[name]
            ]
            for place in sorted(roles.open - roles.start - roles.clocks)
        }

    def _counted_places(self, views: Mapping[str, _View]) -> dict[str, int]:
        """Places the net only counts (ADR 0062), and how many tokens each
        keeps: no arc takes from it, its arcs test only how many tokens it
        holds (no predicate or correlate, and no reader sees a token's
        data), and it is not open, final or kept. It keeps at most its
        largest read weight (1 for a zero-test) of equal tokens: more change
        nothing a step can see."""
        roles = self.roles
        arcs: dict[str, list[Arc]] = {}
        for inputs in self.model.inputs.values():
            for arc in inputs:
                if arc.from_place:
                    arcs.setdefault(arc.from_place, []).append(arc)
        found: dict[str, int] = {}
        for place, readers in sorted(arcs.items()):
            if place in roles.open | roles.final | roles.kept:
                continue
            view = views.get(place)
            if view is None or view.paths != () or view.predicates:
                continue
            tests = [arc.consume for arc in readers if arc.consume is not None]
            if any(
                test.mode == "consume" or test.predicate or test.correlate
                for test in tests
            ):
                continue
            found[place] = max(
                test.weight if test.mode == "read" else 1 for test in tests
            )
        return found

    def _saturated(self, marking: Marking) -> Marking:
        """``marking`` with each counted place cut to as many equal tokens
        as its readers count (ADR 0062)."""
        for place, keep in self._counted.items():
            tokens = marking.get(place, ())
            if len(tokens) > keep and len({token_key(t) for t in tokens}) == 1:
                marking = marking.set(place, list(tokens[:keep]))
        return marking

    # ── The environment's tokens ───────────────────────────────────────

    def _prepare_environment(self) -> None:
        roles = self.roles
        for name in sorted(roles.open - roles.clocks):
            place = self.model.places[name]
            tokens: list[Token] = []
            for color in place.accepts:
                # The start token arrives whole: every field the net reads
                # later is set, and the instance's keys are its own.
                own = INSTANCE if name in roles.start else ENVIRONMENT
                for data in self.model.token_variants(
                    color, vary=None, own=own, full=False
                ):
                    tokens.append(Token(color, data))
            # One token per class its readers cannot tell apart, the first
            # in the domains' order (ADR 0061).
            classes: dict[Any, Token] = {}
            for token in tokens:
                classes.setdefault(self._class_of(name, token), token)
            self._env_tokens[name] = list(classes.values())
        for name in sorted(roles.clocks):
            accepts = self.model.places[name].accepts
            color = accepts[0]
            fields = sorted(
                path for path in self.model.known.get(color, set()) if len(path) == 1
            )
            field_name = fields[0][0] if fields else "now"
            domain = self.model.domain(color, (field_name,))
            self._clock_field[name] = field_name
            self._clock_values[name] = tuple(domain.values) if domain else (0,)

    def _class_of(self, place: str, token: Token) -> Any:
        """What the steps that read ``place`` can see of ``token``: its
        color, each arc predicate's answer and every field another reader
        reads (ADR 0061, Decision 2), and, when a step copies it into a side
        output, whether the net's own domains accept the copy (ADR 0065,
        Limit); the whole token when a reader may see all of it, or when
        tokens are not grouped."""
        view = self._views.get(place)
        if view is None or view.paths is None:
            return token_key(token)
        return (
            token.type,
            tuple(
                self.firing.predicate_holds(cel, token)
                for color, cel in view.predicates
                if color == token.type
            ),
            tuple(_value_at(token.data, path) for path in view.paths),
            view.aside and domain_violation(self.net, place, token) is None,
        )

    def initial(self) -> Marking:
        marking = self.model.initial_marking()
        for name in sorted(self.roles.clocks):
            if not marking.get(name):
                color = self.model.places[name].accepts[0]
                value = self._clock_values[name][0]
                marking = marking.set(
                    name, [Token(color, {self._clock_field[name]: value})]
                )
        return marking

    def clock_setup(self) -> list[Move]:
        """The moves that put the initial clock tokens down, for a play."""
        moves: list[Move] = []
        start = self.net.initial_marking or Marking()
        for name in sorted(self.roles.clocks):
            if not start.get(name):
                color = self.model.places[name].accepts[0]
                value = self._clock_values[name][0]
                moves.append(
                    Move(
                        "advance",
                        place=name,
                        token=Token(color, {self._clock_field[name]: value}),
                    )
                )
        return moves

    # ── Exploration ────────────────────────────────────────────────────

    def explore(self) -> None:
        initial = self.initial()
        used: dict[str, int] = {}
        start_marked = any(initial.get(place) for place in self.roles.start) or any(
            token.type == self.roles.instance_color
            for place, tokens in initial.items()
            if place not in self.roles.kept
            for token in tokens
        )
        if start_marked:
            used["start"] = 1
        self._add(self._saturated(initial), tuple(sorted(used.items())), None)
        queue = deque([0])
        queued = {0}
        progress = self.progress
        while queue:
            index = queue.popleft()
            state = self.states[index]
            if state.final:
                continue
            if len(self.states) >= self.max_states:
                self.capped = True
                break
            self._expand(index)
            state.expanded = True
            for _, target, _ in state.edges:
                if target not in queued:
                    queued.add(target)
                    queue.append(target)
            if progress is not None:
                progress.tick(len(self.states), len(queue))

    def _add(
        self,
        marking: Marking,
        used: tuple[tuple[str, int], ...],
        via: tuple[int, int] | None,
    ) -> int:
        marked = frozenset(place for place, tokens in marking.items() if tokens)
        _, live, used_key = self._relevance(marked, used)
        key = (self._marking_keys.key(marking, live, marked), used_key)
        existing = self._ids.get(key)
        if existing is not None:
            return existing
        self._marking_keys.keep()
        index = len(self.states)
        final = self.roles.finished(marking, self.environment.starts)
        self.states.append(_State(marking, used, final=final))
        self._ids[key] = index
        if via is not None:
            self.parent[index] = via
        return index

    def _move(self, move: Move) -> int:
        key = move.key(self._token_text)
        found = self._move_ids.get(key)
        if found is None:
            found = len(self.moves)
            self.moves.append(move)
            self._move_ids[key] = found
        return found

    def _token_text(self, token: Token) -> str:
        # Moves reuse the tokens of kept markings and of Firing's kept
        # outputs, so the text is kept by the token's identity. The entry
        # holds the token, so its id is not reused while the entry lives.
        found = self._token_texts.get(id(token))
        if found is None or found[0] is not token:
            found = (token, token_text(token))
            self._token_texts[id(token)] = found
        return found[1]

    def _relevance(
        self, marked: frozenset[str], used: tuple[tuple[str, int], ...]
    ) -> tuple[set[str], set[str], tuple[tuple[str, int], ...]]:
        """Open places some still-possible transition reads, the places
        whose tokens can still matter, and the counts in ``used`` that do.

        A transition is still possible when each of its input places holds a
        token, can get one from the environment, or is an output of another
        still-possible transition. Tokens in an open place that no such
        transition reads cannot change what happens next, so the explorer
        neither writes there nor tells states apart by them, nor by how
        often the environment wrote there.

        The answer depends only on ``marked`` (the places that hold tokens)
        and on the counts in ``used``, so it is kept per pair.
        """
        found = self._relevances.get((marked, used))
        if found is None:
            relevant, live = self._relevance_of(marked, dict(used))
            counted = tuple(
                (k, v)
                for k, v in used
                if k == "start"
                or k.startswith("fire:")
                or k.split(":", 1)[1] in relevant
            )
            found = self._relevances[(marked, used)] = (relevant, live, counted)
        return found

    def _relevance_of(
        self, marked: frozenset[str], used: Mapping[str, int]
    ) -> tuple[set[str], set[str]]:
        roles = self.roles
        available = {place for place in self.place_names if place in marked}
        for place in roles.open:
            if self._can_arrive(place, used):
                available.add(place)
        possible: set[str] = set()
        changed = True
        while changed:
            changed = False
            for tr in self.net.transitions:
                if tr.name in possible or self._used_up(tr.name, used):
                    continue
                if self._needs[tr.name] <= available:
                    possible.add(tr.name)
                    available |= self._outputs[tr.name]
                    changed = True
        relevant: set[str] = set()
        for name in possible:
            relevant |= self._inputs[name] & roles.open
        # A side output (a sink that is not final, like a signal place) is
        # never read, so its tokens never change what happens next.
        live = (set(self.place_names) - roles.open - roles.side_outputs) | relevant
        return relevant, live

    def _used_up(self, transition: str, used: Mapping[str, int]) -> bool:
        limit = self.environment.firings.get(transition)
        return limit is not None and used.get(f"fire:{transition}", 0) >= limit

    def _can_arrive(self, place: str, used: Mapping[str, int]) -> bool:
        roles = self.roles
        if place in roles.clocks:
            return True
        if place in roles.start:
            return used.get("start", 0) < self.environment.starts
        return used.get(f"inject:{place}", 0) < self.environment.injections.get(
            place, 1
        )

    def _expand(self, index: int) -> None:
        state = self.states[index]
        marking = state.marking
        used = dict(state.used)
        marked = frozenset(place for place, tokens in marking.items() if tokens)
        relevant, _, _ = self._relevance(marked, state.used)
        # Net moves and record moves: firings. The priority policy ranks
        # the net's own moves only. It ranks a transition its firing cap
        # stops too, so the cap only removes behavior and never lets a
        # lower-priority transition fire where it could not.
        firings = self.firing.reservations(marking)
        all_enabled = list(firings)
        enabled = [name for name in all_enabled if name not in self._record_moves]
        if self.priority_mode and enabled:
            top = max(self.priority[name] for name in enabled)
            enabled = [name for name in enabled if self.priority[name] == top]
        record_moves = [name for name in all_enabled if name in self._record_moves]
        for name in enabled + record_moves:
            if self._used_up(name, used):
                state.cut = True
                self.stopped[name] = self.stopped.get(name, 0) + 1
        enabled = [name for name in enabled if not self._used_up(name, used)]
        record_moves = [name for name in record_moves if not self._used_up(name, used)]
        for name in enabled:
            self._fire(index, name, NET, firings[name])
        ticks, withheld = self._ticks(marking, relevant)
        for name, at in withheld:
            self._withheld_states.add(index)
            self.withheld.setdefault(name, set()).add(at)
        # A record change waits while the net has moves of its own and no
        # transition that uses the record has its other inputs: it commutes
        # with those moves, and it can still happen once one does.
        waiting: frozenset[str] = frozenset()
        held: frozenset[str] = frozenset()
        if state.edges or ticks:
            if self.postpone:
                waiting = self._waiting(marking)
            # An arrival waits on the same terms, every open place being one
            # the environment can fill (ADR 0061).
            if self.wait_arrivals:
                held = self._waiting_arrivals(marked)
        for name in record_moves:
            if self._inputs[name] | self._outputs[name] <= waiting:
                self.held_moves.add(name)
                continue
            self._fire(index, name, RECORD, firings[name])
        # Net moves: time passes, only when a timer on the clock could fire
        # now or later: a advance commutes with every move that does not read
        # the clock, so a later advance reaches the same markings as an early one.
        for clock, token in ticks:
            move = Move("advance", place=clock, token=token)
            self._edge(index, move, marking.set(clock, [token]), state.used, NET)
        # Arrivals and updates. Until the instance starts, the environment
        # starts it, or writes a place that a step can read before the
        # instance is in the net (ADR 0056). Any other write could happen
        # just after the start with the same effect, since nothing reads the
        # place before.
        writable = relevant - self.roles.clocks
        if not self._started(marking, used, bool(enabled)):
            writable &= self.roles.start | self._read_before_start(marking, state.used)
        for place in sorted(writable):
            if place not in held and self._can_arrive(place, used):
                key = "start" if place in self.roles.start else f"inject:{place}"
                after = dict(used)
                after[key] = after.get(key, 0) + 1
                for token in self._env_tokens.get(place, ()):
                    move = Move("inject", place=place, token=token)
                    successor = marking.set(place, [*marking.get(place, ()), token])
                    self._edge(
                        index, move, successor, tuple(sorted(after.items())), ARRIVAL
                    )
            if place in self.roles.read_only and marking.get(place):
                key = f"update:{place}"
                record = place in self.roles.records
                if record and place in waiting:
                    continue
                if record or used.get(key, 0) < self.environment.updates.get(place, 1):
                    after = dict(used)
                    # A record changes without limit, so its count is not kept.
                    if not record:
                        after[key] = after.get(key, 0) + 1
                    # A token of the class the place holds changes nothing a
                    # step can see.
                    current = {
                        self._class_of(place, token) for token in marking.get(place, ())
                    }
                    for token in self._env_tokens.get(place, ()):
                        if {self._class_of(place, token)} == current:
                            continue
                        move = Move("update", place=place, token=token)
                        self._edge(
                            index,
                            move,
                            marking.set(place, [token]),
                            tuple(sorted(after.items())),
                            RECORD if record else UPDATE,
                        )

    def _fire(
        self,
        index: int,
        name: str,
        kind: str,
        reservations: list[FiringReservation],
    ) -> None:
        state = self.states[index]
        marking = state.marking
        fired_used = state.used
        if name in self.environment.firings:
            after = dict(state.used)
            after[f"fire:{name}"] = after.get(f"fire:{name}", 0) + 1
            fired_used = tuple(sorted(after.items()))
        for reservation in reservations:
            consumed = dict(reservation.consumed_tokens)
            for outputs in self.firing.outputs(name, consumed, full=False):
                fired = self.firing.settle(marking, reservation, outputs)
                if fired.error is not None:
                    self.deposit_errors.append(f"[{name}]: {fired.error}")
                    continue
                move = Move(
                    "fire",
                    transition=name,
                    binding=_frozen(reservation.input_tokens),
                    outputs=outputs,
                )
                self._edge(index, move, fired.marking, fired_used, kind)

    def _waiting(self, marking: Marking) -> frozenset[str]:
        """Records no transition can use yet: no transition that reads or
        writes a record of their group has its other binding places marked.
        A group no transition uses never waits."""
        marked = frozenset(place for place, tokens in marking.items() if tokens)
        found = self._waiting_records.get(marked)
        if found is None:
            other = self.roles.records | self.roles.clocks
            found = frozenset(
                record
                for members, users in self._record_users.items()
                if users
                and not any(self._needs[name] - other <= marked for name in users)
                for record in members
            )
            self._waiting_records[marked] = found
        return found

    def _waiting_arrivals(self, marked: frozenset[str]) -> frozenset[str]:
        """Open places whose arrival waits (ADR 0061): none of their users
        has its binding places marked, open places and clocks aside. It
        depends only on the places no arrival fills."""
        closed = marked - self.roles.open
        found = self._waiting_places.get(closed)
        if found is None:
            other = self.roles.open
            found = frozenset(
                place
                for place, users in self._place_users.items()
                if users
                and not any(self._needs[name] - other <= closed for name in users)
            )
            self._waiting_places[closed] = found
        return found

    def _started(self, marking: Marking, used: Mapping[str, int], busy: bool) -> bool:
        """Whether the instance is in the net, or its start token waits for
        something only the environment can give."""
        if not self.roles.start:
            return True
        if any(marking.get(place) for place in self.roles.instance | self.roles.final):
            return True
        return bool(used.get("start", 0)) and not busy

    def _read_before_start(
        self, marking: Marking, used: tuple[tuple[str, int], ...]
    ) -> frozenset[str]:
        """Open places that a step can read before the instance is in the net.

        A step can fire then when each of its binding places holds a token,
        can get one from the environment (the start aside, unless it is
        already there), or is an output of another such step. A step that
        marks a place of the instance or a final place ends that stretch, so
        its outputs do not count.
        """
        marked = frozenset(place for place, tokens in marking.items() if tokens)
        key = (marked, used)
        found = self._before_start.get(key)
        if found is None:
            counts = dict(used)
            roles = self.roles
            available = set(marked) | {
                place
                for place in roles.open - roles.start
                if self._can_arrive(place, counts)
            }
            entered = roles.instance | roles.final
            possible: set[str] = set()
            changed = True
            while changed:
                changed = False
                for name in self._inputs:
                    if name in possible or self._used_up(name, counts):
                        continue
                    if self._needs[name] <= available:
                        possible.add(name)
                        if not self._outputs[name] & entered:
                            available |= self._outputs[name]
                        changed = True
            found = frozenset(
                place for name in possible for place in self._inputs[name] & roles.open
            )
            self._before_start[key] = found
        return found

    def _timers_ready(self, marking: Marking) -> set[str]:
        """Clock places of timed transitions whose binding places all hold tokens."""
        clocks: set[str] = set()
        for tr in self.net.transitions:
            if tr.timer is None:
                continue
            if all(marking.get(place) for place in self._needs[tr.name]):
                clocks.add(tr.timer.clock)
        return clocks

    def _ticks(
        self, marking: Marking, relevant: set[str]
    ) -> tuple[list[tuple[str, Token]], list[tuple[str, int | float]]]:
        """The clock tokens time can move to from this marking: a later time
        slot, or the time a timer on the clock declares it matures at (its
        ``timer maturity``). A deadline dated from the clock (`now + 60`)
        falls on no slot when the clock reached that slot late; its maturity
        names it. Also the maturities withheld here (:meth:`_maturities`),
        each with its transition."""
        ticks: list[tuple[str, Token]] = []
        withheld: list[tuple[str, int | float]] = []
        for clock in sorted(self.roles.clocks & relevant & self._timers_ready(marking)):
            tokens = marking.get(clock)
            if not tokens:
                continue
            field_name = self._clock_field[clock]
            now = tokens[0].data.get(field_name)
            if not isinstance(now, (int, float)):
                continue
            maturities = self._maturities(marking, clock, now, withheld)
            later = sorted(
                {value for value in self._clock_values[clock] if value > now}
                | maturities
            )
            if not later:
                continue
            if self.postpone and not self._timer_can_fire(
                marking, clock, tokens[0], [now, *later]
            ):
                continue
            for value in later:
                ticks.append(
                    (
                        clock,
                        Token(tokens[0].type, {**tokens[0].data, field_name: value}),
                    )
                )
        return ticks, withheld

    def _maturities(
        self,
        marking: Marking,
        clock: str,
        now: int | float,
        withheld: list[tuple[str, int | float]],
    ) -> set[int | float]:
        """The times after ``now`` that the timers on ``clock`` declare they
        mature at in ``marking``; a whole time stays an int beside an int
        clock.

        A maturity that reads a time the net took from the clock — a straight
        copy (``since``, latched from ``clock.now``) or a deadline dated from
        it (``double(clock.now) + 120``) — counts only while every such latch
        holds one of the clock's listed times. A latch taken at a maturity
        would date the next maturity later still, and time would never run
        out of new values. A maturity left out is appended to ``withheld``."""
        found: set[int | float] = set()
        for maturity in self.firing.engine.timer_maturities(self.net, marking):
            if maturity.clock != clock or maturity.at <= now:
                continue
            at = maturity.at
            at = int(at) if isinstance(now, int) and at.is_integer() else at
            if self._copies_listed(marking, maturity.transition, clock):
                found.add(at)
            else:
                withheld.append((maturity.transition, at))
        return found

    def _copies_listed(self, marking: Marking, transition: str, clock: str) -> bool:
        """Whether every clock latch ``transition``'s maturity reads holds one
        of ``clock``'s listed times, in each token its timer may bind.

        A straight copy is the latch. A deadline dated from the clock
        (``now + offset``) latches ``value - offset``."""
        listed = self._clock_values[clock]
        for copy in self.model.maturity_copies.get(transition, ()):
            for token in marking.get(copy.place, ()):
                if token.type != copy.field.color:
                    continue
                value = _at(token.data, copy.field.path)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    return False
                if value - copy.offset not in listed:
                    return False
        return True

    def _timer_can_fire(
        self, marking: Marking, clock: str, token: Token, values: Sequence[Any]
    ) -> bool:
        """Whether some timer on ``clock`` is enabled with the clock ``token``
        set to one of ``values``, the other places as they are."""
        field_name = self._clock_field[clock]
        for name in self._timed[clock]:
            if not all(marking.get(place) for place in self._needs[name]):
                continue
            key = (
                name,
                tuple(
                    (
                        place,
                        tuple(
                            sorted(self._token_text(t) for t in marking.get(place, ()))
                        ),
                    )
                    for place in sorted(self._inputs[name] - {clock})
                ),
                tuple(values),
            )
            found = self._timer_checks.get(key)
            if found is None:
                found = any(
                    self.firing.can_fire(
                        marking.set(
                            clock,
                            [Token(token.type, {**token.data, field_name: value})],
                        ),
                        name,
                    )
                    for value in values
                )
                self._timer_checks[key] = found
            if found:
                return True
        return False

    def _edge(
        self,
        index: int,
        move: Move,
        marking: Marking,
        used: tuple[tuple[str, int], ...],
        kind: str,
    ) -> None:
        move_id = self._move(move)
        target = self._add(self._saturated(marking), used, (index, move_id))
        self.states[index].edges.append((move_id, target, kind))

    # ── What made the markings ─────────────────────────────────────────

    def made_by(self) -> dict[str, Any]:
        """What made the markings of a run stopped at the state cap
        (proofs.md, What made the markings): the ten steps that first
        reached the most of them, one entry for the rest, and the places
        that multiply them most."""
        tally: Counter[tuple[str, str, str]] = Counter()
        moves = self.moves
        for kind, move_id, count in self._first_steps():
            tally[self._step(kind, moves[move_id])] += count
        reached = sum(tally.values())
        ranked = sorted(tally.items(), key=lambda item: (-item[1], item[0]))

        def entry(step: tuple[str, str, str], count: int) -> dict[str, Any]:
            kind, role, name = step
            return {
                "kind": kind,
                role: name,
                "count": count,
                "share": round(count / reached, 4),
            }

        found: dict[str, Any] = {
            "markings": reached,
            "steps": [entry(step, count) for step, count in ranked[:10]],
        }
        rest = ranked[10:]
        if rest:
            count = sum(count for _, count in rest)
            found["rest"] = {
                "steps": len(rest),
                "count": count,
                "share": round(count / reached, 4),
            }
        found["places"] = [
            {"place": place, "factor": factor}
            for place, factor in self._place_factors()[:10]
        ]
        return found

    def _first_steps(self) -> list[tuple[str, int, int]]:
        """Each step (its kind and move) that first reached a marking, and
        how many markings it first reached."""
        tally: Counter[tuple[str, int]] = Counter()
        states = self.states
        for index, (source, move_id) in self.parent.items():
            kind = next(
                k for m, t, k in states[source].edges if m == move_id and t == index
            )
            tally[kind, move_id] += 1
        return [(kind, move_id, count) for (kind, move_id), count in tally.items()]

    @staticmethod
    def _step(kind: str, move: Move) -> tuple[str, str, str]:
        """A step as the list names it: its kind, and the transition or
        place it acts on."""
        if move.kind == "fire":
            assert move.transition is not None
            kind_name = "record" if kind == RECORD else "firing"
            return (kind_name, "transition", move.transition)
        assert move.place is not None
        if kind == NET:
            return ("advance", "place", move.place)
        named = {ARRIVAL: "arrival", UPDATE: "update", RECORD: "record"}
        return (named[kind], "place", move.place)

    def _place_factors(self) -> list[tuple[str, float]]:
        """Each place whose contents multiply the markings, by how many
        markings become one when the place is ignored, the largest first."""
        total, counts = self._place_counts()
        factors: list[tuple[str, float]] = []
        for place, without in counts:
            factor = round(total / without, 1)
            if factor > 1.0:
                factors.append((place, factor))
        factors.sort(key=lambda item: (-item[1], item[0]))
        return factors

    def _place_counts(self) -> tuple[int, list[tuple[str, int]]]:
        """How many markings were stored, and for each place that varies
        among them, how many distinct markings are left when it is ignored.

        One pass over the stored markings' keys gives each a sum of one
        random 64-bit weight per (place, contents) and per count of uses;
        the key without a place is the sum less that place's weight, so
        each place's count of distinct keys is one set of integers. Two
        different keys share a sum with odds near n² / 2⁶⁵ (one in three
        million at 3.6 million markings): a factor may be off by one
        marking in that many runs, which the list, rounded to a tenth,
        does not show.
        """
        total = len(self._ids)
        draw = random.Random(0).getrandbits
        ids: dict[str, dict[Any, int]] = {}
        weights: dict[str, list[int]] = {}
        columns: dict[str, array[int]] = {}
        used_weights: dict[Any, int] = {}
        sums: list[int] = []
        for row, (places, used) in enumerate(self._ids):
            weight = used_weights.get(used)
            if weight is None:
                weight = used_weights[used] = draw(64)
            total_weight = weight
            for place, contents in places:
                place_ids = ids.get(place)
                if place_ids is None:
                    place_ids = ids[place] = {}
                    # Content id 0, weight 0: the place is not in the key.
                    weights[place] = [0]
                    columns[place] = array("I", bytes(4 * total))
                found = place_ids.get(contents)
                if found is None:
                    found = place_ids[contents] = len(weights[place])
                    weights[place].append(draw(64))
                columns[place][row] = found
                total_weight += weights[place][found]
            sums.append(total_weight)
        counts: list[tuple[str, int]] = []
        for place, column in columns.items():
            place_weights = weights[place]
            if len(place_weights) <= 2 and 0 not in column:
                continue  # one contents in every marking: it multiplies nothing
            without = len(
                set(map(int.__sub__, sums, map(place_weights.__getitem__, column)))
            )
            counts.append((place, without))
        return total, counts

    # ── Checking ───────────────────────────────────────────────────────

    def size(self) -> tuple[int, int]:
        """How many markings and edges the exploration holds."""
        return len(self.states), sum(len(s.edges) for s in self.states)

    def marking(self, index: int) -> Marking:
        """The marking of state ``index``."""
        return self.states[index].marking

    def path_to(self, index: int) -> list[int]:
        """The moves of a shortest path from the net's initial marking: the
        clock setup first, then the explored moves in BFS order."""
        return [self._move(move) for move in self.clock_setup()] + self._parent_moves(
            index
        )

    def _parent_moves(self, index: int) -> list[int]:
        """The explored moves that first reached state ``index``."""
        moves: list[int] = []
        while index in self.parent:
            index, move = self.parent[index]
            moves.append(move)
        moves.reverse()
        return moves

    def _net_successors(self, index: int) -> list[tuple[int, int]]:
        return [(m, t) for m, t, kind in self.states[index].edges if kind == NET]

    def check(self) -> list[Proof]:
        """The three soundness facts, read from what the graph shows."""
        verdict = self._verdict()
        return [
            self._option_to_complete(verdict),
            self._proper_completion(verdict),
            self._dead_transitions(verdict),
        ]

    def _verdict(self) -> Verdict:
        states = self.states
        # A cut marking still has a net move, the one its cap stopped, so it
        # is never a stop.
        quiet = [
            i
            for i, state in enumerate(states)
            if state.expanded
            and not state.final
            and not state.cut
            and not self._net_successors(i)
        ]
        finals = [i for i, state in enumerate(states) if state.final]
        good = self._good(finals, quiet)
        # Past a cut marking the net may still complete, so a marking that
        # reaches one is not refuted; it is not proved good either. So may a
        # marking whose timer matures at a time left out (:meth:`_maturities`):
        # it is a stop, as for a timer due past every listed time, but one
        # that time may still end.
        cuts = [
            i
            for i, state in enumerate(states)
            if state.cut or i in self._withheld_states
        ]
        hopeful = self._good(finals + cuts, quiet) if cuts else good
        bad = next(
            (i for i, state in enumerate(states) if state.expanded and not hopeful[i]),
            None,
        )
        verdict = Verdict(
            all_good=all(good[i] for i, state in enumerate(states) if state.expanded),
            bad=bad,
            improper=next(
                (
                    i
                    for i, state in enumerate(states)
                    if state.final
                    and any(state.marking.get(p) for p in self.roles.instance)
                ),
                None,
            ),
            fired=frozenset(
                m
                for state in states
                for m, _, kind in state.edges
                if kind in (NET, RECORD) and self.moves[m].kind == "fire"
            ),
        )
        if bad is None:
            return verdict
        quiet_set = set(quiet)
        reach = self._net_reach(bad)
        dead = [i for i in reach if i in quiet_set]
        rescues = self._rescues(reach, hopeful)
        if dead:
            end = min(dead, key=lambda i: reach[i][0])
            return replace(
                verdict,
                stop=True,
                end=end,
                tail=tuple(_moves_to(reach, end)),
                rescues=rescues,
            )
        end, tail, cycle = self._find_cycle(bad)
        return replace(
            verdict, end=end, tail=tuple(tail), cycle=tuple(cycle), rescues=rescues
        )

    def _good(self, seeds: Sequence[int], quiet: Sequence[int]) -> list[bool]:
        """Markings from which net moves reach a seed, or stop where an
        arrival or a record change leads on to a good marking."""
        states = self.states
        reverse: list[list[int]] = [[] for _ in states]
        for i, state in enumerate(states):
            for _, target, kind in state.edges:
                if kind == NET:
                    reverse[target].append(i)
        good = [False] * len(states)

        def spread(starts: Iterable[int]) -> None:
            stack = [s for s in starts if not good[s]]
            for s in stack:
                good[s] = True
            while stack:
                node = stack.pop()
                for pred in reverse[node]:
                    if not good[pred]:
                        good[pred] = True
                        stack.append(pred)

        spread(seeds)
        while True:
            waiting = [
                i
                for i in quiet
                if not good[i]
                and any(
                    kind in (ARRIVAL, RECORD) and good[t]
                    for _, t, kind in states[i].edges
                )
            ]
            if not waiting:
                break
            spread(waiting)
        return good

    def _stopped_text(self) -> str:
        return ", ".join(
            f"[{name}] (at {self.environment.firings[name]})"
            for name in sorted(self.stopped)
        )

    def _withheld_text(self) -> str:
        return ", ".join(
            f"[{name}]'s maturity at {', '.join(str(at) for at in sorted(times))}"
            for name, times in sorted(self.withheld.items())
        )

    def _withheld_reason(self) -> str:
        return (
            f"time was not moved to {self._withheld_text()}, dated from a time "
            "copied from the clock that the clock's values do not list"
        )

    def _option_to_complete(self, verdict: Verdict) -> Proof:
        statement = (
            "From every reachable marking, net moves (firings and time) reach a "
            "final marking, or the net stops and a first arrival from the "
            "environment lets it go on to one."
        )
        if not self.roles.final:
            return Proof(
                "soundness",
                "option to complete",
                "unknown",
                statement,
                reason="the net has no final place (a sink of the instance color or "
                "an output port); name the final places in the domains file",
            )
        if verdict.bad is None:
            if self.capped:
                return Proof(
                    "soundness",
                    "option to complete",
                    "unknown",
                    statement,
                    reason=f"the state cap ({self.max_states}) was hit before every marking was explored",
                )
            if not verdict.all_good:
                ways: list[str] = []
                if self.stopped:
                    ways.append(
                        "by firing "
                        + " or ".join(
                            f"[{name}] more often than its firing cap "
                            f"({self.environment.firings[name]}) allows"
                            for name in sorted(self.stopped)
                        )
                    )
                if self.withheld:
                    ways.append(f"past a maturity: {self._withheld_reason()}")
                return Proof(
                    "soundness",
                    "option to complete",
                    "unknown",
                    statement,
                    reason="some markings reach a final marking, if at all, only "
                    + " or ".join(ways),
                )
            return Proof("soundness", "option to complete", "proved", statement)
        end, tail, cycle = verdict.end, list(verdict.tail), list(verdict.cycle)
        if verdict.stop:
            kind = "deadlock"
            marking = self.marking(end)
            held = sorted(
                p for p in self.roles.instance | self.roles.final if marking.get(p)
            )
            if held:
                summary = (
                    "The net stops with the instance in "
                    + ", ".join(f"({p})" for p in held)
                    + ", and no arrival from the environment lets it complete."
                )
            else:
                kind = "vanished"
                summary = (
                    "The instance leaves the net without reaching a final marking: "
                    "no place of the instance holds a token and no final place is marked."
                )
        else:
            kind = "livelock"
            names: list[str] = []
            for move_id in cycle:
                move = self.moves[move_id]
                if move.transition is not None and move.transition not in names:
                    names.append(move.transition)
            if names:
                summary = (
                    "The net can keep firing ("
                    + ", ".join(f"[{n}]" for n in names)
                    + ") but never reaches a final marking unless the environment acts."
                )
            else:
                # A capped search leaves markings unexpanded, so net moves can
                # end there without closing a loop or reaching a stop.
                summary = (
                    "Net moves from here reach no final marking among the "
                    "markings explored, and no loop or stop was found either."
                )
        rescue = self._rescue_words(verdict.rescues)
        if rescue:
            summary += " It completes after " + " or ".join(rescue) + "."
        path = self.path_to(verdict.bad) + tail
        status = "refuted"
        reason = None
        if self.capped:
            # A marking past the cap was never expanded, so the arrival that
            # rescues this one may simply not have been explored yet.
            status, reason = "unknown", f"the state cap ({self.max_states}) was hit"
        finding = Finding(
            kind=kind,
            summary=summary,
            path=tuple(self.moves[m] for m in path),
            cycle=tuple(self.moves[m] for m in cycle),
            marking=_marking_json(self.marking(end)),
        )
        return Proof(
            "soundness",
            "option to complete",
            status,
            statement,
            findings=(finding,),
            reason=reason,
        )

    def _rescues(
        self, reach: Mapping[int, Any], hopeful: list[bool]
    ) -> frozenset[tuple[int, str]]:
        """The moves other than net moves, and their kinds, that lead from
        a marking of ``reach`` to a hopeful one."""
        return frozenset(
            (move_id, kind)
            for index in reach
            for move_id, target, kind in self.states[index].edges
            if kind != NET and hopeful[target]
        )

    def _rescue_words(self, rescues: Iterable[tuple[int, str]]) -> list[str]:
        found: set[str] = set()
        for move_id, kind in rescues:
            move = self.moves[move_id]
            if move.kind == "fire":
                found.add(f"[{move.transition}]")
            elif kind == RECORD:
                assert move.place is not None
                place = self.model.places[move.place]
                label = f"{place.description} " if place.description else ""
                found.add(f"a change of {label}({move.place})")
            else:
                word = "an arrival in" if kind == ARRIVAL else "an update of"
                found.add(f"{word} ({move.place})")
        return sorted(found)

    def _net_reach(self, start: int) -> dict[int, tuple[int, int, int]]:
        """States net moves reach from ``start``: each one's distance, and
        the state and move it was first reached by (``-1`` for ``start``)."""
        seen: dict[int, tuple[int, int, int]] = {start: (0, -1, -1)}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            distance = seen[node][0]
            for move_id, target in self._net_successors(node):
                if target not in seen:
                    seen[target] = (distance + 1, node, move_id)
                    queue.append(target)
        return seen

    def _find_cycle(self, start: int) -> tuple[int, list[int], list[int]]:
        """The nearest state on a loop of net moves from ``start``, the moves
        that reach it, and the shortest loop back to it."""
        reach = self._net_reach(start)
        looping = self._on_loops(reach)
        for node in sorted(reach, key=lambda i: (reach[i][0], i)):
            if node not in looping:
                continue
            for move_id, target in self._net_successors(node):
                if target == node:
                    return node, _moves_to(reach, node), [move_id]
            back = self._net_reach(node)
            _, pred, move_id = min(
                (back[pred][0], pred, move_id)
                for pred in back
                for move_id, target in self._net_successors(pred)
                if target == node and pred != node
            )
            return node, _moves_to(reach, node), _moves_to(back, pred) + [move_id]
        return start, [], []

    def _on_loops(self, reach: Mapping[int, Any]) -> set[int]:
        """The states of ``reach`` that net moves lead back to: those with a
        move to themselves, and those in a strongly connected component of
        two or more (Tarjan's algorithm, without recursion)."""
        number: dict[int, int] = {}
        low: dict[int, int] = {}
        stack: list[int] = []
        stacked: set[int] = set()
        found: set[int] = set()

        def visit(node: int) -> list[int]:
            number[node] = low[node] = len(number)
            stack.append(node)
            stacked.add(node)
            return [target for _, target in self._net_successors(node)]

        for root in reach:
            if root in number:
                continue
            work = [(root, iter(visit(root)))]
            while work:
                node, targets = work[-1]
                deeper = None
                for target in targets:
                    if target == node:
                        found.add(node)
                    if target not in number:
                        deeper = target
                        break
                    if target in stacked:
                        low[node] = min(low[node], number[target])
                if deeper is not None:
                    work.append((deeper, iter(visit(deeper))))
                    continue
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[node])
                if low[node] == number[node]:
                    members: list[int] = []
                    while True:
                        member = stack.pop()
                        stacked.discard(member)
                        members.append(member)
                        if member == node:
                            break
                    if len(members) > 1:
                        found.update(members)
        return found

    def _proper_completion(self, verdict: Verdict) -> Proof:
        statement = "When a final marking is reached, no other place of the instance holds a token."
        if verdict.improper is not None:
            marking = self.marking(verdict.improper)
            left = sorted(p for p in self.roles.instance if marking.get(p))
            finding = Finding(
                kind="improper",
                summary=(
                    "A final marking is reached while "
                    + ", ".join(f"({p})" for p in left)
                    + " still hold tokens of the instance."
                ),
                path=tuple(self.moves[m] for m in self.path_to(verdict.improper)),
                marking=_marking_json(marking),
            )
            return Proof(
                "soundness",
                "proper completion",
                "refuted",
                statement,
                findings=(finding,),
            )
        if self.capped:
            return Proof(
                "soundness",
                "proper completion",
                "unknown",
                statement,
                reason=f"the state cap ({self.max_states}) was hit",
            )
        return Proof("soundness", "proper completion", "proved", statement)

    def _dead_transitions(self, verdict: Verdict) -> Proof:
        statement = "Every transition fires in some reachable marking."
        fired = {self.moves[m].transition for m in verdict.fired}
        # A record move held back where it was enabled can fire there.
        fired |= self.held_moves
        dead = [tr.name for tr in self.net.transitions if tr.name not in fired]
        if not dead:
            return Proof("soundness", "no dead transitions", "proved", statement)
        if self.stopped:
            # A transition the caps kept out of reach may fire on a later turn.
            return Proof(
                "soundness",
                "no dead transitions",
                "unknown",
                statement,
                reason=f"the firing cap stopped {self._stopped_text()}; not fired "
                "within the caps: " + ", ".join(f"[{d}]" for d in dead),
            )
        if self.withheld:
            # A transition past a withheld maturity may fire once time gets there.
            return Proof(
                "soundness",
                "no dead transitions",
                "unknown",
                statement,
                reason=f"{self._withheld_reason()}; not fired before it: "
                + ", ".join(f"[{d}]" for d in dead),
            )
        if self.capped:
            return Proof(
                "soundness",
                "no dead transitions",
                "unknown",
                statement,
                reason=f"the state cap ({self.max_states}) was hit; not fired so far: "
                + ", ".join(f"[{d}]" for d in dead),
            )
        findings = tuple(
            Finding(kind="dead", summary=f"[{name}] never fires.", transition=name)
            for name in dead
        )
        return Proof(
            "soundness", "no dead transitions", "refuted", statement, findings=findings
        )


@dataclass(frozen=True)
class Verdict:
    """What the soundness checks found on an exploration's graph, as the
    numbers of its markings and moves (P15); the explorer names them.

    ``bad`` is the first expanded marking from which no hope of completing
    is left; ``all_good`` says whether every expanded marking completes
    without a cap or a withheld maturity. From ``bad``, net moves (``tail``)
    reach ``end``: a stop when ``stop``, else a marking on a loop of net
    moves (``cycle``); ``rescues`` are the other moves, and their kinds,
    that lead on from where net moves reach to a hopeful marking.
    ``improper`` is the first final marking with the instance still in the
    net, and ``fired`` the fire moves some net or record move took."""

    all_good: bool
    bad: int | None
    improper: int | None
    fired: frozenset[int]
    stop: bool = False
    end: int = 0
    tail: tuple[int, ...] = ()
    cycle: tuple[int, ...] = ()
    rescues: frozenset[tuple[int, str]] = frozenset()


def _moves_to(reach: Mapping[int, tuple[int, int, int]], node: int) -> list[int]:
    """The moves of the path ``reach`` found to ``node``."""
    moves: list[int] = []
    _, parent, move = reach[node]
    while parent >= 0:
        moves.append(move)
        _, parent, move = reach[parent]
    moves.reverse()
    return moves


def _frozen(
    binding: Mapping[str, Sequence[Token]],
) -> tuple[tuple[str, tuple[Token, ...]], ...]:
    return tuple((place, tuple(tokens)) for place, tokens in binding.items())


def _marking_json(
    marking: Mapping[str, Sequence[Token]],
) -> dict[str, list[dict[str, Any]]]:
    return {
        place: [{"type": t.type, "data": t.data} for t in tokens]
        for place, tokens in sorted(marking.items())
        if tokens
    }


_Path = tuple[str | int, ...]


@dataclass
class _View:
    """What the steps can see of a token in one place (ADR 0061, Decision
    2): the CEL predicate of each arc from it, by the arc's color, and the
    fields any other reader reads, or ``None`` when one may read it whole.
    ``aside`` when a step copies its tokens into a side output, which reads
    none of their fields but has the engine check them (ADR 0065)."""

    predicates: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    paths: tuple[_Path, ...] | None = ()
    aside: bool = False


def _views(net: Net, model: NetModel) -> dict[str, _View]:
    """The view of every place a step reads: its arc predicates, and the
    fields read by correlates, timers, produce ``data cel`` and handler
    outputs. A reader the scan cannot follow sees the whole token; a handler
    output into a side output sees none of it (ADR 0065)."""
    reads = _Reads()
    # Colors a handler output may copy from: one that embeds a token, and
    # one that is embedded.
    copied = {color for color, _ in model.embeds} | set(model.embeds.values())
    side_outputs = model.roles.side_outputs
    for tr in net.transitions:
        arcs = model.inputs.get(tr.name, ())
        bound = [
            arc.from_place
            for arc in arcs
            if arc.from_place and arc.consume and arc.consume.mode != "inhibit"
        ]
        names = tr.binding_names
        if tr.guard is not None:
            for place in bound:
                reads.whole(place)
        for arc in arcs:
            consume, place = arc.consume, arc.from_place
            if consume is None or place is None:
                continue
            reads.read(place, None)
            predicate = consume.predicate
            if predicate is not None and predicate.handler:
                reads.whole(place)
            elif predicate is not None and predicate.cel:
                reads.predicates.setdefault(place, []).append(
                    (consume.type, predicate.cel)
                )
            if consume.correlate:
                reads.scan(consume.correlate, [place, *bound], {"token": place}, names)
        if tr.timer is not None:
            bind = dict(tr.timer.bind or {})
            for cel in (tr.timer.cel, tr.timer.maturity):
                if cel is not None:
                    reads.scan(cel, [*bind.values(), *bound], bind, names)
        # Handler outputs by color: into a place a step can read, and into
        # a side output, whose copy no step sees (ADR 0065).
        handler_colors: set[str] = set()
        aside_colors: set[str] = set()
        for arc in model.outputs.get(tr.name, ()):
            produce = arc.produce
            if produce is None:
                continue
            if produce.cel is not None:
                reads.scan(produce.cel, bound, {}, names)
            elif produce.data is None:
                (
                    aside_colors
                    if produce.destination in side_outputs
                    else handler_colors
                ).add(produce.type)
        # A handler output starts from a consumed token of its color (the
        # carry rule), or copies a token embedded in, or embedding, another,
        # which the engine checks under the copy's own color.
        if handler_colors or aside_colors:
            for arc in arcs:
                consume = arc.consume
                if consume is None or not arc.from_place or consume.mode == "inhibit":
                    continue
                if consume.type in handler_colors or consume.type in copied:
                    reads.whole(arc.from_place)
                elif consume.type in aside_colors:
                    reads.aside.add(arc.from_place)
    return {
        place: _View(
            reads.predicates.get(place, []),
            None if found is None else tuple(sorted(found, key=repr)),
            place in reads.aside,
        )
        for place, found in reads.paths.items()
    }


class _Reads:
    """The fields read per place while the views are built; ``None`` for a
    place some reader may read whole. ``aside`` holds the places whose
    tokens a step copies into a side output."""

    def __init__(self) -> None:
        self.predicates: dict[str, list[tuple[str, str]]] = {}
        self.paths: dict[str, set[_Path] | None] = {}
        self.aside: set[str] = set()

    def whole(self, place: str) -> None:
        self.paths[place] = None

    def read(self, place: str, path: _Path | None) -> None:
        """Note that a step reads ``place``, and ``path`` of its tokens."""
        found = self.paths.setdefault(place, set())
        if path is not None and not path:
            self.whole(place)
        elif path is not None and found is not None:
            found.add(path)

    def scan(
        self,
        cel: str,
        places: Sequence[str],
        roots: Mapping[str, str],
        names: Mapping[str, str] | None,
    ) -> None:
        """What ``cel`` reads. ``roots`` names the variables that stand for
        one token of a place (``token``, a timer's bind), ``names`` the
        binding keys; an expression the scan cannot parse reads every place
        it can see whole."""
        tree = celscan.parse(cel)
        if isinstance(tree, Opaque) and not tree.refs:
            for place in places:
                self.whole(place)
            return
        for ref in celscan.refs(tree):
            if ref.root in roots:
                self.read(roots[ref.root], ref.path)
                continue
            if (
                ref.root != "binding"
                or not ref.path
                or not isinstance(ref.path[0], str)
            ):
                continue
            key = ref.path[0]
            place = names.get(key) if names is not None else key
            if place is None:
                continue
            if len(ref.path) < 3 or not isinstance(ref.path[1], int):
                self.whole(place)
            else:
                self.read(place, ref.path[2:])


def _value_at(data: Any, path: _Path) -> str:
    """The JSON text of the value at ``path``, or a mark that it is missing."""
    current: Any = data
    for part in path:
        if isinstance(current, list) and isinstance(part, int):
            items = cast(list[Any], current)
            if not -len(items) <= part < len(items):
                return "⟨missing⟩"
            current = items[part]
        elif isinstance(current, dict) and isinstance(part, str):
            fields = cast(dict[str, Any], current)
            if part not in fields:
                return "⟨missing⟩"
            current = fields[part]
        else:
            return "⟨missing⟩"
    return json.dumps(current, sort_keys=True, ensure_ascii=False)


def explore(
    net: Net,
    model: NetModel,
    *,
    environment: Environment,
    max_states: int,
    postpone: bool = True,
    wait_arrivals: bool = False,
    group_tokens: bool = True,
    saturate: bool = True,
    progress: Progress | None = None,
) -> Explorer:
    explorer = Explorer(
        net,
        model,
        Firing(net, model),
        environment=environment,
        max_states=max_states,
        postpone=postpone,
        wait_arrivals=wait_arrivals,
        group_tokens=group_tokens,
        saturate=saturate,
        progress=progress,
    )
    explorer.explore()
    return explorer


def soundness_proofs(
    net: Net,
    model: NetModel,
    *,
    environment: Environment,
    max_states: int,
    wait_arrivals: bool = False,
    progress: Callable[[str], object] | None = None,
    fast: bool = False,
    one_core: bool = False,
    on_reference: Callable[[str], None] | None = None,
) -> tuple[list[Proof], Explorer]:
    """The three soundness facts, made unknown where the exploration could
    not see every behavior (a named guard or predicate, a failed deposit).
    ``wait_arrivals`` holds an arrival back while no step can use it (ADR
    0061, opt-in). ``progress`` takes the exploration's progress lines.
    ``fast`` explores on the fast path (``fast.py``), on every core or, with
    ``one_core``, on one in the reference's order; a net its tables
    cannot carry is explored by the reference instead, and
    ``on_reference`` is told why (D14). A failure inside the kernel raises
    ``FastPathError`` (D16)."""
    lines = None if progress is None else Progress(net.name, max_states, progress)
    explorer: Explorer | None = None
    if fast:
        from .fast import explore_fast
        from .tables import Untabled

        try:
            explorer = explore_fast(
                net,
                model,
                environment=environment,
                max_states=max_states,
                wait_arrivals=wait_arrivals,
                progress=lines,
                one_core=one_core,
            )
        except Untabled as why:
            if on_reference is not None:
                on_reference(str(why))
    if explorer is None:
        explorer = explore(
            net,
            model,
            environment=environment,
            max_states=max_states,
            wait_arrivals=wait_arrivals,
            progress=lines,
        )
    found = explorer.check()
    # A refutation's path is a path of the net without the caps too, but
    # it may need every start.
    assumptions = environment.assumptions()
    starts = environment.start_assumptions()
    if assumptions or starts:
        found = [
            replace(
                proof,
                assumptions=starts + (assumptions if proof.status != "refuted" else ()),
            )
            for proof in found
        ]
    if model.unsupported:
        reason = "; ".join(
            f"[{name}]: " + ", ".join(why)
            for name, why in sorted(model.unsupported.items())
        )
        found = [
            replace(
                proof,
                status="unknown",
                reason=f"never enabled here, so findings may not hold: {reason}",
            )
            if proof.status != "unknown"
            else proof
            for proof in found
        ]
    if model.unplaced_timers:
        reason = "; ".join(
            f"[{name}]: " + ", ".join(why)
            for name, why in sorted(model.unplaced_timers.items())
        )
        found = [
            replace(
                proof,
                status="unknown",
                reason=f"the exploration cannot tell when a timer fires, so "
                f"findings may not hold: {reason}",
            )
            if proof.status != "unknown"
            else proof
            for proof in found
        ]
    if explorer.deposit_errors:
        errors = sorted(set(explorer.deposit_errors))
        found = [
            replace(
                proof,
                status="unknown",
                reason="a deposit failed on a built token: " + "; ".join(errors[:3]),
            )
            if proof.status == "proved"
            else proof
            for proof in found
        ]
    return found, explorer
