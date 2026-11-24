import {describe, expect, it} from "vitest";
import {Engine} from "@velocitron/runtime";
import {HandlerRegistry} from "@velocitron/engine";
import type {Marking, Net, Timer} from "@velocitron/engine";
import {completed, parsedNet, token} from "./helpers.js";

// Correlated consume and read arcs: `correlate` as a join (ADR 0030). Every
// token the arc binds must make the expression exactly true over
// `{token, binding}`, where `binding` is the whole assembled candidate.

const PLACES = [
  {name: "orders", accepts: ["order"]},
  {name: "settings", accepts: ["setting"]},
  {name: "couriers", accepts: ["courier"]},
  {name: "pauses", accepts: ["pause"]},
  {name: "clock", accepts: ["tick"]},
];
const SAME_ACCOUNT = {cel: "token.account == binding.orders[0].account"};
const SAME_REGION = {cel: "token.region == binding.orders[0].region"};

function arc(place: string, type: string, consume: Record<string, unknown> = {}) {
  return {from: {place}, to: {transition: "ship"}, consume: {type, mode: "consume", weight: 1, ...consume}};
}

function net(arcs: unknown[], timer?: Timer): Net {
  return parsedNet({
    name: "correlated-arcs",
    places: PLACES,
    transitions: [{name: "ship", handler: "ship", ...(timer === undefined ? {} : {timer})}],
    arcs,
  });
}

function settingsNet(correlate: {cel: string} = SAME_ACCOUNT): Net {
  return net([arc("orders", "order"), arc("settings", "setting", {mode: "read", correlate})]);
}

const engine = () => new Engine(new HandlerRegistry());

describe("correlated consume and read arcs", () => {
  it("binds the read settings of the order's own account and skips the rest", () => {
    // given: an order for account B and settings for A then B
    const marking: Marking = {
      orders: [token("order", {account: "B"})],
      settings: [token("setting", {account: "A"}), token("setting", {account: "B"})],
    };

    // when: selecting a binding
    const binding = engine().selectBinding(settingsNet(), "ship", marking);

    // then: the A settings miss the join and the B settings are bound
    expect(binding).toEqual({
      orders: [token("order", {account: "B"})],
      settings: [token("setting", {account: "B"})],
    });
  });

  it("is not enabled when no token correlates", () => {
    // given: an order whose account has no settings token
    const marking: Marking = {
      orders: [token("order", {account: "C"})],
      settings: [token("setting", {account: "A"})],
    };

    // when/then: no binding survives
    expect(engine().selectBinding(settingsNet(), "ship", marking)).toBeNull();
    expect(engine().enabledTransitions(settingsNet(), marking)).toEqual([]);
  });

  it("sees a later arc from a correlate on an earlier consume arc", () => {
    // given: the correlated courier arc is declared before the order arc
    const correlated = net([arc("couriers", "courier", {correlate: SAME_REGION}), arc("orders", "order")]);
    const marking: Marking = {
      orders: [token("order", {region: "west"})],
      couriers: [token("courier", {region: "east"}), token("courier", {region: "west"})],
    };

    // when: selecting a binding
    const binding = engine().selectBinding(correlated, "ship", marking);

    // then: the binding is assembled before the check, so the west courier joins
    expect(binding?.couriers).toEqual([token("courier", {region: "west"})]);
  });

  it("requires every token of a weighted arc to correlate", () => {
    // given: a weight-2 correlated consume arc and three couriers
    const correlated = net([arc("orders", "order"), arc("couriers", "courier", {weight: 2, correlate: SAME_REGION})]);
    const marking: Marking = {
      orders: [token("order", {region: "west"})],
      couriers: [
        token("courier", {id: 1, region: "west"}),
        token("courier", {id: 2, region: "east"}),
        token("courier", {id: 3, region: "west"}),
      ],
    };

    // when: selecting a binding
    const binding = engine().selectBinding(correlated, "ship", marking);

    // then: the first pair with two west couriers is (1, 3)
    expect(binding?.couriers?.map((courier) => courier.data.id)).toEqual([1, 3]);
  });

  it("applies the single-token predicate before the correlate", () => {
    // given: a courier arc with both a predicate and a correlate
    const correlated = net([
      arc("orders", "order"),
      arc("couriers", "courier", {predicate: {cel: "available"}, correlate: SAME_REGION}),
    ]);
    const marking: Marking = {
      orders: [token("order", {region: "west"})],
      couriers: [
        token("courier", {id: 1, available: false, region: "west"}),
        token("courier", {id: 2, available: true, region: "east"}),
        token("courier", {id: 3, available: true, region: "west"}),
      ],
    };

    // when: selecting a binding
    const binding = engine().selectBinding(correlated, "ship", marking);

    // then: courier 1 fails the predicate and courier 2 fails the correlate
    expect(binding?.couriers?.map((courier) => courier.data.id)).toEqual([3]);
  });

  it("fails closed on eval errors and non-boolean results", () => {
    // given: a correlate over a missing field and one returning a string
    const marking: Marking = {
      orders: [token("order", {account: "A"})],
      settings: [token("setting", {account: "A"})],
    };
    const missing = settingsNet({cel: "token.missing == binding.orders[0].account"});
    const nonBoolean = settingsNet({cel: "token.account"});

    // when/then: neither binding survives, and nothing throws
    expect(engine().selectBinding(missing, "ship", marking)).toBeNull();
    expect(engine().selectBinding(nonBoolean, "ship", marking)).toBeNull();
  });

  it("lets a correlated inhibit see the joined read token", () => {
    // given: settings joined to the order, and a pause keyed by carrier
    const correlated = net([
      arc("orders", "order"),
      arc("settings", "setting", {mode: "read", correlate: SAME_ACCOUNT}),
      {from: {place: "pauses"}, to: {transition: "ship"}, consume: {
        type: "pause",
        mode: "inhibit",
        weight: 1,
        correlate: {cel: "token.carrier == binding.settings[0].carrier"},
      }},
    ]);
    const marking: Marking = {
      orders: [token("order", {account: "A"}), token("order", {account: "B"})],
      settings: [
        token("setting", {account: "A", carrier: "post"}),
        token("setting", {account: "B", carrier: "van"}),
      ],
      pauses: [token("pause", {carrier: "post"})],
    };

    // when: selecting a binding
    const binding = engine().selectBinding(correlated, "ship", marking);

    // then: (A, B settings) misses the join, (A, A settings) is paused, B ships
    expect(binding).toEqual({
      orders: [token("order", {account: "B"})],
      settings: [token("setting", {account: "B", carrier: "van"})],
    });
  });

  it("feeds a timer bind only the correlated token", () => {
    // given: A settings mature at 10, B settings at 50, order B, clock 20
    const timed = net(
      [
        arc("orders", "order", {mode: "read"}),
        arc("settings", "setting", {mode: "read", correlate: SAME_ACCOUNT}),
        arc("clock", "tick", {mode: "read"}),
      ],
      {
        clock: "clock",
        cel: "clock.now >= settings.ship_at",
        bind: {settings: "settings"},
        maturity: "settings.ship_at",
      },
    );
    const registry = new HandlerRegistry();
    registry.registerTransition("ship", () => completed());
    const marking: Marking = {
      orders: [token("order", {account: "B"})],
      settings: [
        token("setting", {account: "A", ship_at: 10}),
        token("setting", {account: "B", ship_at: 50}),
      ],
      clock: [token("tick", {now: 20})],
    };

    // when: asking for enablement and the next wake
    const timedEngine = new Engine(registry);

    // then: the matured A settings never reach the timer; B's 50 is the wake
    expect(timedEngine.enabledTransitions(timed, marking)).toEqual([]);
    expect(timedEngine.timerMaturities(timed, marking)).toEqual([{transition: "ship", clock: "clock", at: 50}]);
  });
});
