"""The fast path's tables: what each rule of a net means for each token, as
the reference explorer answers it.

The kernel (``velocitron_kernel``) explores a net alone over token ids. It
never evaluates CEL or fires a handler: every answer it needs comes from a
row filled here, by the same engine and the same ``Firing`` the reference
explorer uses, so the reference stays the only code that says what a rule
means (D8). The rows are (P14):

- per token: each arc's test (its color and predicate), its reader class in
  each read-only place, whether it holds a listed time where a timer's
  maturity reads a clock copy, and the time it shows if it is a clock token;
- each correlate for each pair of tokens: the arc's token and the token the
  correlate reads from another arc of the binding;
- each binding's tokens taken and made, per handler output;
- each timer's hold and maturity per clock token and bound tokens, and the
  clock token each later time makes;
- the environment's tokens, and the explorer's roles.

Before the run :func:`fill` fills the roles and the rows of the tokens the
run starts from: the initial marking's and the environment's. Every other
row is filled on first use (D14): the kernel asks :class:`Rows` for it the
first time a marking needs it, in the same process, and a row that makes a
new token brings that token's rows with it. So the tables hold the rows the
run uses, and no other: a net whose tokens are dated from the clock has no
end of rows before the run, and only as many as its markings need during it.

A net that uses what the tables cannot carry yet (a guard, a predicate
handler, an arc of weight above one, a correlate that reads more than one
other arc, more than 64 places) is :class:`Untabled`, and so is a run that
meets more than ``TOKEN_LIMIT`` tokens.

References: the spec's P14, D8, D14, D15; ``measure.md`` § 3.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from velocitron_engine import Arc, Marking, Token

from . import celscan
from .celscan import Opaque
from .report import Move
from .soundness import Explorer, _frozen  # pyright: ignore[reportPrivateUsage]

TOKEN_LIMIT = 65_000
"""The most tokens a run's tables may hold: the kernel keeps a token as a
16-bit id."""

MAX_PLACES = 64
MAX_BINDING_ARCS = 6

Effect = tuple[list[tuple[int, int]], list[tuple[int, int]]]
TokenRow = tuple[list[bool], list[int], list[list[bool]], int | None]
Update = tuple[list[TokenRow], list[float]]


class Untabled(Exception):
    """The net uses something the tables cannot carry; the reference explores
    it."""


class TooManyTokens(Untabled):
    """The run met more tokens than the kernel can number."""


def _field(value: Any, part: str | int) -> Any:
    """``value``'s field ``part``, or None when it has none."""
    if isinstance(value, dict):
        return cast(dict[Any, Any], value).get(part)
    return None


class _Fire:
    """One binding's row, as the reference names its moves."""

    def __init__(
        self,
        transition: str,
        binding: Mapping[str, Sequence[Token]],
        outputs: list[Any],
        errors: list[str | None],
    ) -> None:
        self.transition = transition
        self.binding = binding
        self.outputs = outputs
        self.errors = errors


class Rows:
    """The tables of one net for one exploration, and the reference that
    fills their rows on first use.

    ``kernel`` is what crosses to the kernel before the run, in memory. The
    kernel calls :meth:`fire`, :meth:`corr`, :meth:`timer` and :meth:`tick`
    for each row it lacks; each answers the row and an :data:`Update` with
    the rows of any token or time the row made. The rest stays here to name
    what comes back: ``tokens[i]`` is token ``i``, ``fires[r]`` fire row
    ``r``, ``values[v]`` a clock time."""

    def __init__(self, explorer: Explorer, limit: int = TOKEN_LIMIT) -> None:
        self.explorer = explorer
        self.limit = limit
        self.net = explorer.net
        self.model = explorer.model
        self.firing = explorer.firing
        self.engine = explorer.firing.engine
        self.places = explorer.place_names
        self.pid = {p: i for i, p in enumerate(self.places)}
        self.transitions = list(self.net.transitions)
        self.tr_id = {tr.name: i for i, tr in enumerate(self.transitions)}
        self.binding_arcs: dict[str, tuple[Arc, ...]] = {}
        self.inhibit_arcs: dict[str, tuple[Arc, ...]] = {}
        self.anchors: dict[tuple[str, str], int | None] = {}
        self.tokens: list[Token] = []
        self.token_ids: dict[str, int] = {}
        self.values: list[Any] = []
        self.value_ids: dict[tuple[str, Any], int] = {}
        self.fires: list[_Fire] = []
        # Each arc test in the kernel's order; each correlate's arc.
        self.tests: list[Arc] = []
        self.corrs: list[tuple[str, int, bool]] = []
        self.copies: list[list[tuple[str, Any, tuple[Any, ...], int | float]]] = []
        self.read_only = sorted(explorer.roles.read_only)
        self.class_ids: dict[str, int] = {}
        self.counts = {"fire": 0, "corr": 0, "timer": 0, "tick": 0}
        self._sent_tokens = 0
        self._sent_values = 0
        self._check()
        self.used_names = self._used_names()
        self.kernel = self._kernel()

    # ── Checks ─────────────────────────────────────────────────────────

    def _check(self) -> None:
        ex, net = self.explorer, self.net
        if len(self.places) > MAX_PLACES:
            raise Untabled(f"the net has {len(self.places)} places, over {MAX_PLACES}")
        for tr in net.transitions:
            if tr.guard is not None:
                raise Untabled(f"[{tr.name}] has a guard")
            binding = self.engine._binding_arcs(net, tr.name)  # pyright: ignore[reportPrivateUsage]
            inhibit = self.engine._input_arcs(net, tr.name, "inhibit")  # pyright: ignore[reportPrivateUsage]
            if len(binding) > MAX_BINDING_ARCS:
                raise Untabled(
                    f"[{tr.name}] has {len(binding)} binding arcs, over {MAX_BINDING_ARCS}"
                )
            for arc in (*binding, *inhibit):
                consume = arc.consume
                assert consume is not None
                if consume.weight != 1:
                    raise Untabled(f"[{tr.name}] has an arc of weight {consume.weight}")
                if consume.predicate is not None and consume.predicate.handler:
                    raise Untabled(f"[{tr.name}] has a predicate handler")
                if consume.correlate is not None:
                    self._anchor(tr.name, consume.correlate, binding)
            if tr.timer is not None:
                bind_places = {a.from_place for a in binding}
                for var, place in (tr.timer.bind or {}).items():
                    if place not in bind_places:
                        raise Untabled(
                            f"[{tr.name}]'s timer binds {var} from an unbound place"
                        )
            self.binding_arcs[tr.name] = binding
            self.inhibit_arcs[tr.name] = inhibit
        if any(p in ex.roles.clocks for p in ex._counted):  # pyright: ignore[reportPrivateUsage]
            raise Untabled("a clock is a counted place")

    def _anchor(self, name: str, cel: str, binding: Sequence[Arc]) -> int | None:
        """The binding arc whose token a correlate reads, or None when it
        reads no other arc. A correlate reading more is not tabled."""
        key = (name, cel)
        if key not in self.anchors:
            self.anchors[key] = self._read_anchor(name, cel, binding)
        return self.anchors[key]

    def _read_anchor(self, name: str, cel: str, binding: Sequence[Arc]) -> int | None:
        tree = celscan.parse(cel)
        if isinstance(tree, Opaque) and not tree.refs:
            raise Untabled(f"[{name}] has a correlate the scan cannot read: {cel}")
        names = next(t for t in self.net.transitions if t.name == name).binding_names
        keys: set[str] = set()
        for ref in celscan.refs(tree):
            if ref.root != "binding":
                continue
            if (
                len(ref.path) < 2
                or ref.path[1] != 0
                or not isinstance(ref.path[0], str)
            ):
                raise Untabled(
                    f"[{name}] has a correlate that reads a whole binding list: {cel}"
                )
            keys.add(ref.path[0])
        if len(keys) > 1:
            raise Untabled(
                f"[{name}] has a correlate that reads {len(keys)} arcs: {cel}"
            )
        if not keys:
            return None
        read = keys.pop()
        place = names.get(read) if names is not None else read
        for index, arc in enumerate(binding):
            if arc.from_place == place:
                return index
        return None

    # ── Tokens and times ───────────────────────────────────────────────

    def token(self, token: Token) -> int:
        """The id of ``token``, numbering it if new."""
        text = self.explorer._token_text(token)  # pyright: ignore[reportPrivateUsage]
        found = self.token_ids.get(text)
        if found is None:
            if len(self.tokens) >= self.limit:
                raise TooManyTokens(f"the run met more than {self.limit} tokens")
            found = self.token_ids[text] = len(self.tokens)
            self.tokens.append(token)
        return found

    def _value(self, value: Any) -> int:
        key = (type(value).__name__, value)
        found = self.value_ids.get(key)
        if found is None:
            found = self.value_ids[key] = len(self.values)
            self.values.append(value)
        return found

    def _test(self, arc: Arc, token: Token) -> bool:
        consume = arc.consume
        assert consume is not None
        if token.type != consume.type:
            return False
        if consume.predicate is None or not consume.predicate.cel:
            return True
        return self.firing.predicate_holds(consume.predicate.cel, token)

    def _token_row(self, token: Token) -> TokenRow:
        ex = self.explorer
        classes = [0] * len(self.places)
        for place in self.read_only:
            key = repr(ex._class_of(place, token))  # pyright: ignore[reportPrivateUsage]
            classes[self.pid[place]] = self.class_ids.setdefault(
                key, len(self.class_ids)
            )
        copies: list[list[bool]] = []
        for rows in self.copies:
            ok: list[bool] = []
            for _place, item, listed, offset in rows:
                value: Any = token.data
                for part in item.path:
                    value = _field(value, part)
                latch: Any = value
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    latch = value - offset
                ok.append(token.type != item.color or latch in listed)
            copies.append(ok)
        now = None
        for clock in ex.roles.clocks:
            if token.type == self.model.places[clock].accepts[0]:
                value = token.data.get(ex._clock_field[clock])  # pyright: ignore[reportPrivateUsage]
                if isinstance(value, (int, float)):
                    now = self._value(value)
        return ([self._test(arc, token) for arc in self.tests], classes, copies, now)

    def update(self) -> Update:
        """The rows of the tokens and times made since the last update."""
        tokens: list[TokenRow] = []
        while self._sent_tokens < len(self.tokens):
            tokens.append(self._token_row(self.tokens[self._sent_tokens]))
            self._sent_tokens += 1
        values = [
            float(v) if isinstance(v, (int, float)) else float("nan")
            for v in self.values[self._sent_values :]
        ]
        self._sent_values = len(self.values)
        return tokens, values

    # ── Rows on first use: the kernel calls these ──────────────────────

    def corr(self, c: int, tid: int, anchor_tid: int | None) -> tuple[bool, Update]:
        """A correlate's answer: for a consume or read arc, whether it passes
        (only ``true``); for an inhibit arc, whether it blocks (anything but
        ``false``, an error included), as the engine reads them."""
        self.counts["corr"] += 1
        name, index, inhibit = self.corrs[c]
        arcs = self.inhibit_arcs[name] if inhibit else self.binding_arcs[name]
        consume = arcs[index].consume
        assert consume is not None and consume.correlate is not None
        anchor = self._anchor(name, consume.correlate, self.binding_arcs[name])
        bound: dict[str, list[Token]] = {}
        if anchor is not None and anchor_tid is not None:
            bound[self.binding_arcs[name][anchor].from_place or ""] = [
                self.tokens[anchor_tid]
            ]
        engine = self.engine
        try:
            result = engine._cel_adapter.eval(  # pyright: ignore[reportPrivateUsage, reportUnknownMemberType]
                engine._compile_cel(consume.correlate),  # pyright: ignore[reportPrivateUsage]
                {
                    "token": self.tokens[tid].data,
                    "binding": engine._cel_binding(self.net, name, bound),  # pyright: ignore[reportPrivateUsage]
                },
            )
        except Exception:  # noqa: BLE001 - an eval error fails closed, as in the engine
            found = inhibit
        else:
            found = result is not False if inhibit else result is True
        return found, self.update()

    def _grouped(
        self, name: str, arcs: Sequence[int], tids: Sequence[int]
    ) -> dict[str, list[Token]]:
        binding = self.binding_arcs[name]
        grouped: dict[str, list[Token]] = {}
        for index, tid in zip(arcs, tids, strict=True):
            grouped.setdefault(binding[index].from_place or "", []).append(
                self.tokens[tid]
            )
        return grouped

    def timer(self, t: int, c: int, bind: list[int]) -> tuple[bool, int | None, Update]:
        """Whether transition ``t``'s timer holds with clock token ``c`` and
        ``bind`` bound to its variables, and if not, the time it matures at
        (a later one than the clock shows), or None."""
        self.counts["timer"] += 1
        tr = self.transitions[t]
        timer = tr.timer
        assert timer is not None
        binding = self.binding_arcs[tr.name]
        arcs = [
            next(i for i, a in enumerate(binding) if a.from_place == place)
            for place in dict(timer.bind or {}).values()
        ]
        grouped = self._grouped(tr.name, arcs, bind)
        clock = self.tokens[c]
        engine = self.engine
        holds = engine._timer_holds(timer, clock.data, grouped)  # pyright: ignore[reportPrivateUsage]
        maturity: int | None = None
        if not holds and timer.maturity is not None:
            at = engine._timer_maturity(timer, clock.data, grouped, transition=tr.name)  # pyright: ignore[reportPrivateUsage]
            now = clock.data.get(self.explorer._clock_field.get(timer.clock, "now"))  # pyright: ignore[reportPrivateUsage]
            if at is not None and isinstance(now, (int, float)) and not at <= now:
                value = int(at) if isinstance(now, int) and at.is_integer() else at
                maturity = self._value(value)
        return holds, maturity, self.update()

    def tick(self, clock: int, c: int, v: int) -> tuple[int, Update]:
        """The token clock token ``c`` becomes when time moves to ``v``."""
        self.counts["tick"] += 1
        place = self.places[clock]
        token = self.tokens[c]
        field_name = self.explorer._clock_field[place]  # pyright: ignore[reportPrivateUsage]
        tid = self.token(Token(token.type, {**token.data, field_name: self.values[v]}))
        return tid, self.update()

    def fire(
        self, t: int, combo: list[int], clock: int | None
    ) -> tuple[int, list[Effect | None], Update]:
        """Transition ``t`` fired with ``combo`` bound to its binding arcs (and
        clock token ``clock`` when its timer's clock is not bound): its row,
        each handler output's tokens taken and made."""
        self.counts["fire"] += 1
        tr = self.transitions[t]
        name = tr.name
        grouped = self._grouped(name, range(len(combo)), combo)
        marking = Marking()
        for place, toks in grouped.items():
            marking = marking.set(place, list(toks))
        if tr.timer is not None and tr.timer.clock not in grouped and clock is not None:
            marking = marking.set(tr.timer.clock, [self.tokens[clock]])
        firing = self.firing
        reservation = firing.reserve(marking, name, grouped)
        if reservation is None:
            raise Untabled(f"[{name}]: a binding its gates pass could not be reserved")
        consumed = dict(reservation.consumed_tokens)
        rest = {p: list(marking.get(p) or []) for p in marking}
        for p, toks in consumed.items():
            for token in toks:
                rest[p].remove(token)
        outputs = firing.outputs(name, consumed, full=False)
        removed = [
            (self.pid[p], self.token(x)) for p, toks in consumed.items() for x in toks
        ]
        effects: list[Effect | None] = []
        errors: list[str | None] = []
        for output in outputs:
            fired = firing.settle(marking, reservation, output)
            if fired.error is not None:
                effects.append(None)
                errors.append(f"[{name}]: {fired.error}")
                continue
            added: list[tuple[int, int]] = []
            for p, toks in fired.marking.items():
                toks = list(toks or [])
                kept = rest.get(p, [])
                if toks[: len(kept)] != kept:
                    raise Untabled(f"[{name}]'s deposit reorders the tokens of ({p})")
                added += [(self.pid[p], self.token(x)) for x in toks[len(kept) :]]
            effects.append((removed, added))
            errors.append(None)
        row = len(self.fires)
        self.fires.append(_Fire(name, reservation.input_tokens, list(outputs), errors))
        return row, effects, self.update()

    # ── Naming what comes back ─────────────────────────────────────────

    def move(self, kind: int, a: int, b: int) -> Move:
        """The reference's move for the kernel's ``(kind, a, b)``."""
        if kind == 0:
            row = self.fires[a]
            return Move(
                "fire",
                transition=row.transition,
                binding=_frozen(row.binding),
                outputs=row.outputs[b],
            )
        word = ("inject", "update", "advance")[kind - 1]
        return Move(word, place=self.places[a], token=self.tokens[b])  # pyright: ignore[reportArgumentType]

    def sizes(self) -> dict[str, int]:
        """How many rows the run used: its tokens, times and asked rows."""
        return {
            "tokens": len(self.tokens),
            "clock_times": len(self.values),
            "tests": len(self.tests),
            "test_cells": len(self.tests) * len(self.tokens),
            "fire_rows": self.counts["fire"],
            "fire_outputs": sum(len(f.outputs) for f in self.fires),
            "correlate_rows": self.counts["corr"],
            "timer_rows": self.counts["timer"],
            "tick_rows": self.counts["tick"],
        }

    # ── Before the run ─────────────────────────────────────────────────

    def _used_names(self) -> list[str]:
        roles, env = self.explorer.roles, self.explorer.environment
        return sorted(
            {"start"}
            | {f"fire:{n}" for n in env.firings}
            | {f"inject:{p}" for p in roles.open - roles.start - roles.clocks}
            | {f"update:{p}" for p in roles.read_only}
        )

    def _kernel(self) -> dict[str, Any]:
        ex, net, pid = self.explorer, self.net, self.pid
        roles, env = ex.roles, ex.environment

        def mask(places: Any) -> int:
            m = 0
            for p in places:
                m |= 1 << pid[p]
            return m

        uid = {k: i for i, k in enumerate(self.used_names)}
        transitions: list[dict[str, Any]] = []
        for tr in net.transitions:
            binding = self.binding_arcs[tr.name]

            def arc_row(
                arc: Arc, index: int, inhibit: bool, tr: Any = tr
            ) -> dict[str, Any]:
                self.tests.append(arc)
                corr = None
                consume = arc.consume
                assert consume is not None
                if consume.correlate is not None:
                    corr = len(self.corrs)
                    self.corrs.append((tr.name, index, inhibit))
                return {
                    "place": pid[arc.from_place or ""],
                    "test": len(self.tests) - 1,
                    "corr": corr,
                }

            timer = None
            if tr.timer is not None:
                timer = {
                    "clock": pid[tr.timer.clock],
                    "bind": [
                        next(i for i, a in enumerate(binding) if a.from_place == place)
                        for place in dict(tr.timer.bind or {}).values()
                    ],
                    "maturity": tr.timer.maturity is not None,
                }
            copies: list[tuple[str, Any, tuple[Any, ...], int | float]] = []
            if tr.timer is not None:
                listed = tuple(ex._clock_values.get(tr.timer.clock, ()))  # pyright: ignore[reportPrivateUsage]
                for copy in self.model.maturity_copies.get(tr.name, ()):
                    copies.append((copy.place, copy.field, listed, copy.offset))
            self.copies.append(copies)
            limit = env.firings.get(tr.name)
            transitions.append(
                {
                    "priority": ex.priority[tr.name],
                    "cap": (uid[f"fire:{tr.name}"], limit)
                    if limit is not None
                    else None,
                    "record_move": tr.name in ex._record_moves,  # pyright: ignore[reportPrivateUsage]
                    "binding": [arc_row(a, i, False) for i, a in enumerate(binding)],
                    "inhibit": [
                        arc_row(a, i, True)
                        for i, a in enumerate(self.inhibit_arcs[tr.name])
                    ],
                    "timer": timer,
                    "copies": [pid[place] for place, _item, _listed, _offset in copies],
                    "needs": mask(ex._needs[tr.name]),  # pyright: ignore[reportPrivateUsage]
                    "inputs": mask(ex._inputs[tr.name]),  # pyright: ignore[reportPrivateUsage]
                    "outputs": mask(ex._outputs[tr.name]),  # pyright: ignore[reportPrivateUsage]
                }
            )
        corrs = [
            {
                "anchor": self._anchor(
                    name,
                    cast(
                        str,
                        (self.inhibit_arcs if inhibit else self.binding_arcs)[name][
                            index
                        ].consume.correlate,  # pyright: ignore[reportOptionalMemberAccess]
                    ),
                    self.binding_arcs[name],
                )
            }
            for name, index, inhibit in self.corrs
        ]
        clocks = [
            {
                "place": pid[clock],
                "listed": [self._value(v) for v in ex._clock_values[clock]],  # pyright: ignore[reportPrivateUsage]
            }
            for clock in sorted(roles.clocks)
        ]
        initial = ex.initial()
        initial_ids = [[self.token(t) for t in initial.get(p, ())] for p in self.places]
        env_ids = [
            [self.token(t) for t in ex._env_tokens.get(p, ())]  # pyright: ignore[reportPrivateUsage]
            for p in self.places
        ]
        start_marked = any(initial.get(p) for p in roles.start) or any(
            token.type == roles.instance_color
            for place, tokens in initial.items()
            if place not in roles.kept
            for token in tokens
        )
        tr_id = self.tr_id
        return {
            "places": len(self.places),
            "transitions": transitions,
            "tests": len(self.tests),
            "corrs": corrs,
            "clocks": clocks,
            "update": self.update(),
            "open": mask(roles.open),
            "start": mask(roles.start),
            "records": mask(roles.records),
            "read_only": mask(roles.read_only),
            "entered": mask(roles.instance | roles.final),
            "sinks": mask(roles.sinks),
            "final_places": mask(roles.final),
            "by_name": sorted(range(len(self.places)), key=lambda i: self.places[i]),
            "injections": [env.injections.get(p, 1) for p in self.places],
            "updates": [env.updates.get(p, 1) for p in self.places],
            "env_tokens": env_ids,
            "counted": [(pid[p], keep) for p, keep in ex._counted.items()],  # pyright: ignore[reportPrivateUsage]
            "record_groups": [
                (mask(members), [tr_id[n] for n in users])
                for members, users in ex._record_users.items()  # pyright: ignore[reportPrivateUsage]
            ],
            "place_users": [
                (pid[p], [tr_id[n] for n in users])
                for p, users in ex._place_users.items()  # pyright: ignore[reportPrivateUsage]
            ],
            "postpone": ex.postpone,
            "wait_arrivals": ex.wait_arrivals,
            "priority_mode": ex.priority_mode,
            "starts": env.starts,
            "final_markings": [[pid[p] for p in fm] for fm in roles.final_markings],
            "used_keys": [
                (
                    k,
                    pid[k.split(":", 1)[1]]
                    if k.startswith(("inject:", "update:"))
                    else None,
                )
                for k in self.used_names
            ],
            "uid_start": uid["start"],
            "uid_inject": [uid.get(f"inject:{p}") for p in self.places],
            "uid_update": [uid.get(f"update:{p}") for p in self.places],
            "initial": initial_ids,
            "initial_used": [(uid["start"], 1)] if start_marked else [],
        }


def fill(explorer: Explorer, *, limit: int = TOKEN_LIMIT) -> Rows:
    """The tables of ``explorer``'s net, filled before the run as far as the
    run's first tokens; the rest are filled on first use."""
    return Rows(explorer, limit)


__all__ = ["TOKEN_LIMIT", "Rows", "TooManyTokens", "Untabled", "fill"]
