import {describe, expect, it} from "vitest";
import {Engine} from "@velocitron/runtime";
import {HandlerRegistry} from "@velocitron/engine";
import type {Marking} from "@velocitron/engine";
import {parsedNet, token} from "./helpers.js";

// The consumption contracts over THE one binding walk (ADR 0027). Mirrors
// implementations/python/tests/test_binding_enumeration.py — the two
// implementations must produce identical primitive semantics; each test here
// pins the same public-surface oracle its Python twin does.

function pollNet(order: "waiting-first" | "clock-first") {
  const waitingArc = {
    from: {place: "waiting"},
    to: {transition: "poll"},
    consume: {type: "work", mode: "read", weight: 1},
  };
  const clockArc = {
    from: {place: "clock"},
    to: {transition: "poll"},
    consume: {type: "tick", mode: "read", weight: 1},
  };
  return parsedNet({
    name: "two-waiters",
    places: [
      {name: "clock", accepts: ["tick"]},
      {name: "waiting", accepts: ["work"]},
    ],
    transitions: [
      {
        name: "poll",
        handler: "poll",
        timer: {
          clock: "clock",
          cel: "clock.now >= work.next_poll_at",
          bind: {work: "waiting"},
          maturity: "work.next_poll_at",
        },
      },
    ],
    arcs: order === "clock-first" ? [clockArc, waitingArc] : [waitingArc, clockArc],
  });
}

const waiterMarking: Marking = {
  clock: [token("tick", {now: 20})],
  waiting: [token("work", {next_poll_at: 30}), token("work", {next_poll_at: 100})],
};

function idBinding(token_?: {data: {id?: string}} | null): string {
  return token_?.data.id as string;
}

describe("the one binding enumeration", () => {
  it("binds declaration/token-order lexicographic pairs with guard-rejected candidates skipped, identically across attempts", () => {
    // given: three tokens and two same-place arcs, with a guard accepting only
    // the (a, c) pair — the walk skips (a, a) as sub-multiset-invalid and
    // (a, b) as guard-rejected before surviving at (a, c)
    const net = parsedNet({
      name: "stable-order",
      places: [{name: "items", accepts: ["task"]}],
      transitions: [{name: "pick", handler: "pick", guard: "pick_ac"}],
      arcs: [
        {from: {place: "items"}, to: {transition: "pick"}, consume: {type: "task", mode: "consume", weight: 1}},
        {from: {place: "items"}, to: {transition: "pick"}, consume: {type: "task", mode: "consume", weight: 1}},
      ],
    });
    const registry = new HandlerRegistry();
    registry.registerGuard("pick_ac", (input) =>
      [idBinding(input.inputTokens.items?.[0] ?? null), idBinding(input.inputTokens.items?.[1] ?? null)]
      .join(",") === "a,c");
    const engine = new Engine(registry);
    const marking: Marking = {"items": [token("task", {id: "a"}), token("task", {id: "b"}), token("task", {id: "c"})]};

    // when: selecting with several attempts, repeatedly
    const attempts = [0, 1, 9].map((attempt) => engine.selectBinding(net, "pick", marking, {attempt}));
    const again = Array.from({length: 3}, () => engine.selectBinding(net, "pick", marking));

    // then: every call yields the identical first surviving binding
    expect(attempts).toEqual(again);
    expect(attempts.map((binding) => [idBinding(binding?.items?.[0] ?? null), idBinding(binding?.items?.[1] ?? null)]))
      .toEqual([["a", "c"], ["a", "c"], ["a", "c"]]);
  });

  it("advances past sub-multiset and correlated-inhibit skips in enumeration order", () => {
    // given: three tokens, two same-place arcs, and a correlated inhibit that
    // blocks every binding whose first id is 'a' — (a, b) and (a, c) are
    // correlated-blocked; (b, a) is the first surviving pair
    const net = parsedNet({
      name: "skip-annotated",
      places: [
        {name: "items", accepts: ["task"]},
        {name: "seen", accepts: ["task"]},
      ],
      transitions: [
        {name: "pick", handler: "pick"},
        {name: "seen", handler: "seen"},
      ],
      arcs: [
        {from: {place: "items"}, to: {transition: "pick"}, consume: {type: "task", mode: "consume", weight: 1}},
        {from: {place: "items"}, to: {transition: "pick"}, consume: {type: "task", mode: "consume", weight: 1}},
        {from: {place: "seen"}, to: {transition: "seen"}, consume: {type: "task", mode: "consume", weight: 1}},
        {
          from: {place: "seen"},
          to: {transition: "pick"},
          consume: {type: "task", mode: "inhibit", correlate: {cel: "token.id == binding.items[0].id"}},
        },
      ],
    });
    const engine = new Engine(new HandlerRegistry());
    const marking: Marking = {
      "items": [token("task", {id: "a"}), token("task", {id: "b"}), token("task", {id: "c"})],
      "seen": [token("task", {id: "a"})],
    };

    // when: selecting a binding for pick
    // then: the first pair past the correlated-blocked ones is (b, a)
    expect(engine.selectBinding(net, "pick", marking)).toEqual({
      "items": [token("task", {id: "b"}), token("task", {id: "a"})],
    });
  });

  it("timerMaturities stops at the first timer-predicate failure — one wake candidate per timed transition", () => {
    // given: a poll reading two waiters with distinct stamped poll times, in
    // declaration order [30, 100], against a clock at 20 — both unmatured
    const net = pollNet("waiting-first");
    const engine = new Engine(new HandlerRegistry());

    // when: reading the wake candidates
    const maturities = engine.timerMaturities(net, waiterMarking);

    // then: exactly the first unmatured binding's maturity, once
    // Bite: the pre-card walk appended a maturity per cel-failing binding
    // (both 30 and 100 here).
    expect(maturities).toEqual([{transition: "poll", clock: "clock", at: 30}]);
    // and: re-reading is order-stable
    expect(engine.timerMaturities(net, waiterMarking)).toEqual(maturities);
  });

  it("timerMaturities walks past ready (cel-holding) bindings to the first unmatured one", () => {
    // given: the same two-waiter net with a matured first waiter (poll time in
    // the past) and a future second waiter
    const net = pollNet("waiting-first");
    const engine = new Engine(new HandlerRegistry());
    const marking: Marking = {
      "clock": [token("tick", {now: 20})],
      "waiting": [token("work", {next_poll_at: 1}), token("work", {next_poll_at: 100})],
    };

    // when: reading the wake candidates
    // then: only the unmatured second waiter is scheduled
    expect(engine.timerMaturities(net, marking)).toEqual([
      {transition: "poll", clock: "clock", at: 100},
    ]);
  });

  it("keeps the identical first-failure record when the clock arc is declared first", () => {
    // given: the same timers with the clock arc declared first — the product's
    // outer loop order changes, the first unmatured binding does not
    const net = pollNet("clock-first");
    const engine = new Engine(new HandlerRegistry());

    // when: reading the wake candidates
    // then: the same single record survives
    expect(engine.timerMaturities(net, waiterMarking)).toEqual([
      {transition: "poll", clock: "clock", at: 30},
    ]);
  });
});