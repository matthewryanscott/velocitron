import assert from "node:assert/strict";
import test from "node:test";

import {HandlerRegistry} from "@velocitron/engine";
import {Runtime, TokenArrival} from "../dist/index.js";

const celAdapter = {
  compile(source) {
    return source;
  },
  evaluate() {
    return false;
  },
};

function moveNet(marking) {
  return {
    name: "runtime",
    places: [
      {name: "inbox", accepts: ["job"]},
      {name: "outbox", accepts: ["job"]},
    ],
    transitions: [{name: "work", handler: "work"}],
    arcs: [
      {from: {place: "inbox"}, to: {transition: "work"}, consume: {type: "job", mode: "consume", weight: 1}},
      {from: {transition: "work"}, to: {place: "outbox"}, produce: {type: "job", destination: "outbox"}},
    ],
    initialMarking: marking,
  };
}

function completed(place, data) {
  return async () => ({
    status: "completed",
    outputTokens: {[place]: [{type: "job", data}]},
    error: null,
    metadata: {},
  });
}

test("runtime rejects a handlerless transition", () => {
  // given: a transition with no handler reference
  const net = {
    name: "runtime",
    places: [],
    transitions: [{name: "traditional"}],
    arcs: [],
  };
  // when: constructing a Runtime
  // then: the missing handler is reported before the spec map is compared
  assert.throws(
    () => new Runtime({
      net,
      handlers: {other: {handler: completed("outbox", {}), lane: "main"}},
      lanes: {main: 1},
      celAdapter,
    }),
    /transitions without handlers: \["traditional"\]/,
  );
});

test("runtime deposits one async firing", async () => {
  // given: one token and a handler that deposits a finished token
  const runtime = new Runtime({
    net: moveNet({inbox: [{type: "job", data: {id: 1}}]}),
    handlers: {work: {handler: completed("outbox", {id: 1, done: true}), lane: "main"}},
    lanes: {main: 1},
    celAdapter,
  });
  // when: the run loop admits the enabled transition
  await runtime.start();
  await runtime.waitIdle();
  await runtime.stop();
  // then: the consumed token is deposited as the handler's output
  assert.deepEqual(runtime.marking.inbox ?? [], []);
  assert.deepEqual(runtime.marking.outbox[0].data, {id: 1, done: true});
});

test("runtime uses the injected firing policy", async () => {
  // given: two transitions that consume the same token, with priorities
  const seen = [];
  const handler = (name) => async (input) => {
    seen.push(input.transitionId);
    return {
      status: "completed",
      outputTokens: {out: [{type: "job", data: {by: name}}]},
      error: null,
      metadata: {},
    };
  };
  const net = {
    name: "runtime",
    places: [
      {name: "inbox", accepts: ["job"]},
      {name: "out", accepts: ["job"]},
    ],
    transitions: [
      {name: "low", handler: "low", priority: 1},
      {name: "high", handler: "high", priority: 5},
    ],
    arcs: [
      {from: {place: "inbox"}, to: {transition: "low"}, consume: {type: "job", mode: "consume", weight: 1}},
      {from: {place: "inbox"}, to: {transition: "high"}, consume: {type: "job", mode: "consume", weight: 1}},
      {from: {transition: "low"}, to: {place: "out"}, produce: {type: "job", destination: "out"}},
      {from: {transition: "high"}, to: {place: "out"}, produce: {type: "job", destination: "out"}},
    ],
    initialMarking: {inbox: [{type: "job", data: {id: 1}}]},
  };
  const runtime = new Runtime({
    net,
    handlers: {
      low: {handler: handler("low"), lane: "main"},
      high: {handler: handler("high"), lane: "main"},
    },
    lanes: {main: 1},
    registry: new HandlerRegistry(),
    policy: "priority",
    celAdapter,
  });
  // when: the run loop admits one of the conflicting transitions
  await runtime.start();
  await runtime.waitIdle();
  await runtime.stop();
  // then: the priority policy selects the higher-priority transition
  assert.deepEqual(seen, ["high"]);
  assert.deepEqual(runtime.marking.out[0].data, {by: "high"});
});

test("cancel stops the other firing in the scope and restores its token", async () => {
  // given: two independent firings that share a scope
  let release;
  const released = new Promise((resolve) => {
    release = resolve;
  });
  let started;
  const startedGate = new Promise((resolve) => {
    started = resolve;
  });
  const slow = async () => {
    started();
    await released;
    return {
      status: "completed",
      outputTokens: {slowOut: [{type: "job", data: {done: true}}]},
      error: null,
      metadata: {},
    };
  };
  const stopper = async (_input, ctx) => {
    await startedGate;
    const cancelled = ctx.cancel("job");
    assert.equal(cancelled.cancelled, 1);
    return {
      status: "completed",
      outputTokens: {stopOut: [{type: "job", data: {done: true}}]},
      error: null,
      metadata: {},
    };
  };
  const net = {
    name: "runtime",
    places: [
      {name: "slowIn", accepts: ["job"]},
      {name: "stopIn", accepts: ["job"]},
      {name: "slowOut", accepts: ["job"]},
      {name: "stopOut", accepts: ["job"]},
    ],
    transitions: [
      {name: "slow", handler: "slow"},
      {name: "stop", handler: "stop"},
    ],
    arcs: [
      {from: {place: "slowIn"}, to: {transition: "slow"}, consume: {type: "job", mode: "consume", weight: 1}},
      {from: {place: "stopIn"}, to: {transition: "stop"}, consume: {type: "job", mode: "consume", weight: 1}},
      {from: {transition: "slow"}, to: {place: "slowOut"}, produce: {type: "job", destination: "slowOut"}},
      {from: {transition: "stop"}, to: {place: "stopOut"}, produce: {type: "job", destination: "stopOut"}},
    ],
    initialMarking: {
      slowIn: [{type: "job", data: {id: "slow"}}],
      stopIn: [{type: "job", data: {id: "stop"}}],
    },
  };
  const runtime = new Runtime({
    net,
    handlers: {
      slow: {handler: slow, lane: "main", scope: () => "job"},
      stop: {handler: stopper, lane: "main", scope: () => "job"},
    },
    lanes: {main: 2},
    celAdapter,
  });
  // when: the stopper cancels the other firing in the scope
  await runtime.start();
  await runtime.waitIdle();
  await runtime.stop();
  // then: the cancelled firing's token is restored and the stopper deposits
  assert.deepEqual(runtime.marking.slowOut ?? [], []);
  assert.deepEqual(runtime.marking.slowIn[0].data, {id: "slow"});
  assert.deepEqual(runtime.marking.stopOut[0].data, {done: true});
  release();
});

test("inject admits a later arrival", async () => {
  // given: an empty inbox and a handler for the arrival
  const runtime = new Runtime({
    net: moveNet({}),
    handlers: {work: {handler: completed("outbox", {id: 7, done: true}), lane: "main"}},
    lanes: {main: 1},
    celAdapter,
  });
  await runtime.start();
  // when: the caller injects the token the transition consumes
  await runtime.inject(new TokenArrival("inbox", {type: "job", data: {id: 7}}));
  await runtime.waitIdle();
  await runtime.stop();
  // then: the injected token was consumed and the output deposited
  assert.deepEqual(runtime.marking.inbox ?? [], []);
  assert.equal(runtime.marking.outbox[0].data.id, 7);
});
