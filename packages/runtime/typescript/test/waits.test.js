import assert from "node:assert/strict";
import test from "node:test";

import {holds, intendedWaits, waitProblems} from "../dist/index.js";

function adapter(compile) {
  return {
    compile,
    evaluate(compiled) {
      return compiled === "true";
    },
  };
}

test("an intended wait holds when the condition is true", () => {
  // given: one wait whose condition the adapter accepts
  const transition = {
    name: "start",
    handler: "start",
    annotations: {wait: {when: "true", for: "a reply"}},
  };
  const cel = adapter((source) => source);
  // when: the wait is read and evaluated
  const found = intendedWaits(transition);
  const held = holds(found[0], {}, {}, cel);
  // then: the annotation is the wait, and the true condition holds
  assert.deepEqual(found.map((item) => [item.when, item.reason]), [["true", "a reply"]]);
  assert.equal(held, true);
});

test("a malformed wait is a problem and declares no wait", () => {
  // given: a wait entry missing the reason
  const transition = {name: "start", handler: "start", annotations: {wait: {when: "true"}}};
  const net = {name: "waits", places: [{name: "inbox", accepts: ["job"]}], transitions: [transition], arcs: []};
  // when: the annotation is read and checked
  // then: it declares no wait, and the problem names the transition
  assert.deepEqual(intendedWaits(transition), []);
  const problems = waitProblems(net, adapter((source) => source));
  assert.equal(problems[0].transition, "start");
  assert.match(problems[0].message, /when/);
});

test("wait problems report CEL that does not compile", () => {
  // given: a well-shaped wait whose CEL the adapter rejects
  const net = {
    name: "waits",
    places: [],
    transitions: [{name: "start", annotations: {wait: {when: "???", for: "a reply"}}}],
    arcs: [],
  };
  // when: the annotation is checked
  const problems = waitProblems(net, adapter(() => {
    throw new Error("syntax");
  }));
  // then: the message says the CEL is not valid
  assert.equal(problems.length, 1);
  assert.equal(problems[0].transition, "start");
  assert.match(problems[0].message, /not valid CEL/);
});

test("holds is false when evaluation fails", () => {
  // given: a wait whose adapter raises while evaluating
  const transition = {name: "start", annotations: {wait: [{when: "true", for: "a reply"}]}};
  const cel = {
    compile: (source) => source,
    evaluate() {
      throw new Error("eval");
    },
  };
  // when: the condition is evaluated
  const held = holds(intendedWaits(transition)[0], {}, {}, cel);
  // then: the failure does not count as the wait holding
  assert.equal(held, false);
});
