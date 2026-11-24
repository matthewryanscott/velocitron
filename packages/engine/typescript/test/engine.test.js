import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  ConflictError,
  Engine,
  EngineConfigurationError,
  FailedAttemptError,
  HandlerRegistry,
  PRIORITY_FIRING_POLICY,
} from "../dist/index.js";

const adapter = {
  compile(source) {
    throw new Error(`compile ${source}`);
  },
  evaluate() {
    throw new Error("evaluate");
  },
};

function moveNet() {
  return {
    name: "move",
    places: [
      {name: "src", accepts: ["job"]},
      {name: "dst", accepts: ["job"]},
    ],
    transitions: [{name: "move", handler: "move"}],
    arcs: [
      {
        from: {place: "src"},
        to: {transition: "move"},
        consume: {type: "job", mode: "consume", weight: 1},
      },
      {
        from: {transition: "move"},
        to: {place: "dst"},
        produce: {type: "job", destination: "dst"},
      },
    ],
  };
}

function splitNet(priorities = {}) {
  const net = moveNet();
  return {
    ...net,
    name: "split",
    transitions: ["a", "b"].map((name) => ({name, handler: name, priority: priorities[name]})),
    arcs: ["a", "b"].flatMap((name) => [
      {from: {place: "src"}, to: {transition: name}, consume: {type: "job", mode: "consume", weight: 1}},
      {from: {transition: name}, to: {place: "dst"}, produce: {type: "job", destination: "dst"}},
    ]),
  };
}

function splitRegistry(a = "completed") {
  const registry = new HandlerRegistry();
  for (const name of ["a", "b"]) {
    registry.registerTransition(name, (input) => {
      const failed = name === "a" && a === "failed";
      return {
        status: failed ? "failed" : "completed",
        outputTokens: failed ? {} : {dst: input.inputTokens.src},
        error: failed ? {type: "Boom", message: "no"} : null,
        metadata: {},
      };
    });
  }
  return registry;
}

describe("engine", () => {
  it("fires a bound transition without calling CEL", () => {
    // given: a handler that moves the bound token
    const registry = new HandlerRegistry();
    registry.registerTransition("move", (input) => {
      const token = input.inputTokens.src[0];
      return {
        status: "completed",
        outputTokens: {dst: [{type: "job", data: {id: token.data.id, done: true}}]},
        error: null,
        metadata: {},
      };
    });
    const engine = new Engine(registry, {celAdapter: adapter});
    const net = moveNet();
    const marking = {src: [{type: "job", data: {id: 1}}]};
    // when: the engine fires the enabled transition
    const enabled = engine.enabledTransitions(net, marking);
    const fired = engine.fire(net, marking, "move", {attempt: 0});
    const ran = engine.run(net, marking, {maxSteps: 4});
    // then: the token is deposited once
    assert.deepEqual(enabled, ["move"]);
    assert.equal(fired.record.status, "completed");
    assert.deepEqual(fired.marking.dst, [{type: "job", data: {id: 1, done: true}}]);
    assert.deepEqual(ran.dst, [{type: "job", data: {id: 1, done: true}}]);
    assert.deepEqual(ran.src, []);
  });

  it("requires an injected adapter", () => {
    // given: a registry and no adapter
    const registry = new HandlerRegistry();
    // when: the engine is constructed without one
    // then: construction fails before any firing
    assert.throws(
      () => new Engine(registry, {}),
      (error) => error instanceof EngineConfigurationError
        && String(error.message).includes("celAdapter is required"),
    );
  });

  it("raises on a conflict in a strict run, and picks first-found by default", () => {
    // given: one job that both [a] and [b] can take
    const engine = new Engine(splitRegistry(), {celAdapter: adapter});
    const marking = {src: [{type: "job", data: {id: 1}}]};
    // when/then: strict raises before any firing, at the marking it started from
    assert.throws(
      () => engine.run(splitNet(), marking, {strict: true}),
      (error) => error instanceof ConflictError
        && error.message === "split: [a], [b] are enabled at once"
        && error.transitions.join() === "a,b"
        && error.marking === marking,
    );
    // and: the default run still fires one of them
    assert.deepEqual(engine.run(splitNet(), marking).dst, [{type: "job", data: {id: 1}}]);
  });

  it("raises on a failed attempt in a strict run", () => {
    // given: [a] outranks [b] under the priority policy, and [a] fails
    const engine = new Engine(splitRegistry("failed"), {
      celAdapter: adapter,
      policy: PRIORITY_FIRING_POLICY,
    });
    const marking = {src: [{type: "job", data: {id: 1}}]};
    // when/then: the resolved conflict passes, the failure raises at the
    // marking the run reached, unchanged by the failed attempt
    assert.throws(
      () => engine.run(splitNet({a: 1}), marking, {strict: true}),
      (error) => error instanceof FailedAttemptError
        && error.message === "split: [a] failed: Boom: no"
        && error.record.status === "failed"
        && error.marking === marking,
    );
    // and: a tie at the top priority is still a conflict
    assert.throws(
      () => engine.run(splitNet({a: 1, b: 1}), marking, {strict: true}),
      (error) => error instanceof ConflictError,
    );
  });

  it("raises a failed attempt from the exception its handler output carries", () => {
    // given: a handler whose failed output carries the exception that failed it
    const gone = new Error("the VM is gone");
    const registry = new HandlerRegistry();
    registry.registerTransition("move", () => ({
      status: "failed",
      outputTokens: {},
      error: {type: "Error", message: "the VM is gone"},
      metadata: {},
      exception: gone,
    }));
    const engine = new Engine(registry, {celAdapter: adapter});
    const marking = {src: [{type: "job", data: {id: 1}}]};
    // when/then: the strict run's error has that exception as its cause, and
    // the record does not hold it
    assert.throws(
      () => engine.run(moveNet(), marking, {strict: true}),
      (error) => error instanceof FailedAttemptError
        && error.cause === gone
        && !("exception" in error.record),
    );
  });

  it("raises a failed attempt from a strict fire, and returns it from a plain one", () => {
    // given: a handler whose failed output carries the exception that failed it
    const gone = new Error("the VM is gone");
    const registry = new HandlerRegistry();
    registry.registerTransition("move", () => ({
      status: "failed",
      outputTokens: {},
      error: {type: "Error", message: "the VM is gone"},
      metadata: {},
      exception: gone,
    }));
    const engine = new Engine(registry, {celAdapter: adapter});
    const marking = {src: [{type: "job", data: {id: 1}}]};
    // when/then: the strict fire throws with that cause, at the unchanged marking
    assert.throws(
      () => engine.fire(moveNet(), marking, "move", {attempt: 0, strict: true}),
      (error) => error instanceof FailedAttemptError
        && error.cause === gone
        && error.marking === marking,
    );
    // and: the plain fire returns the failed record
    assert.equal(engine.fire(moveNet(), marking, "move", {attempt: 0}).record.status, "failed");
  });
});
