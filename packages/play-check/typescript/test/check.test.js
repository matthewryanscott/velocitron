import {mkdtempSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join} from "node:path";
import test from "node:test";
import assert from "node:assert/strict";

import {parsePlay, PlayError} from "@velocitron/play";
import {PlayCheckError, checkPlay, renderWalkthrough, walkthroughDocument} from "../dist/index.js";

const NET = `net shop "Shop"

(orders) -purchase-> [accept] -purchase-> (accepted)

marking initial (orders) <- $o
$o: purchase {"id": "o-1"}
`;

function playAt(body, net = NET) {
  const root = mkdtempSync(join(tmpdir(), "play-check-"));
  writeFileSync(join(root, "shop.petrinet"), net);
  writeFileSync(join(root, "shop.play"), body);
  return {root, play: parsePlay(body, join(root, "shop.play"))};
}

test("checkPlay carries the consumed token and steps a walkthrough", () => {
  // given: a handlerless net and a play that fires the one transition
  const {play} = playAt(
    'play shop "One purchase"\n'
    + 'net "shop.petrinet"\n'
    + "fire [accept]\n"
    + 'expect (accepted) has purchase {"id": "o-1"}\n'
    + "expect (orders) empty\n",
  );
  // when: the package checks the play and renders the path
  const report = checkPlay(play);
  // then: symbolic firing moved the token, and the walkthrough names the step
  assert.equal(report.passed, true);
  const trace = report.traces[0];
  assert.equal(trace.final.accepted[0].data.id, "o-1");
  assert.equal((trace.final.orders ?? []).length, 0);
  const document = walkthroughDocument(trace);
  assert.equal(document.steps[0].statement, "fire [accept]");
  assert.match(renderWalkthrough(trace), /accept/);
});

test("an unknown place is SC202", () => {
  // given: a play that names a place the net does not have
  const {play} = playAt(
    'play shop "Missing"\nnet "shop.petrinet"\ninject (missing) <- purchase {}\n',
  );
  // when: the check resolves the play
  // then: resolution fails before anything plays
  assert.throws(() => checkPlay(play), (error) => error instanceof PlayCheckError && error.code === "SC202");
});

test("a failed expect stops the path", () => {
  // given: a play whose expect does not match the marking after the firing
  const {play} = playAt(
    'play shop "Wrong"\n'
    + 'net "shop.petrinet"\n'
    + "fire [accept]\n"
    + 'expect (orders) has purchase {"id": "o-1"}\n',
  );
  // when: the path plays until the expect
  const report = checkPlay(play);
  // then: the failure is on the trace, not an exception
  assert.equal(report.passed, false);
  const diagnostic = report.diagnostics()[0];
  assert.equal(diagnostic.code, "SC307");
  assert.equal(report.traces[0].failure.diagnostic.code, "SC307");
});

test("an advance leaves a timed handler transition for the author", () => {
  // given: [remind] has a handler; carrying its token would guess its output
  const net = 'net remind "Remind"\n'
    + "(kept) -teardown-> [remind] -teardown-> (asked)\n"
    + "@remind_clock: (clock) -tick->? [remind]\n"
    + '[remind] timer clock (clock) cel "clock.now >= kept.remindAt"\n'
    + "[remind] timer bind kept (kept)\n"
    + '[remind] handler "remind@task_vms"\n'
    + "marking start (kept) <- $k\n"
    + "marking start (clock) <- $c\n"
    + '$k: teardown {"n": 1, "remindAt": 100}\n'
    + '$c: tick {"now": 0}\n';
  const {play} = playAt(
    'play shop "Remind"\nnet "shop.petrinet"\nmarking start\nadvance 100\n'
    + "expect enabled [remind]\n"
    + 'fire [remind] -> (asked) teardown {"n": 2, "remindAt": 100}\n'
    + 'expect (asked) == teardown {"n": 2, "remindAt": 100}\n',
    net,
  );
  // when: the play is checked
  const report = checkPlay(play);
  // then: the advance matured nothing; the author's fire gave the output
  assert.equal(report.passed, true, report.diagnostics().map((d) => d.message).join("\n"));
});

test("a play parse error stays a PlayError from the grammar package", () => {
  // given: source that is not a play
  // when: the grammar package parses it
  // then: the failure is the grammar package's error, not a check
  assert.throws(() => parsePlay("not a play\n"), (error) => error instanceof PlayError);
});
