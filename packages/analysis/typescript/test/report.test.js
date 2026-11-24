import assert from "node:assert/strict";
import test from "node:test";

import {FACTS, ProofReportError, proofReportStatus, readProofReport} from "../dist/index.js";

function report(facts, status = "proved") {
  return {
    version: 1,
    tool: "velocitron 0.1.0",
    net: "sound",
    source: "sound.petrinet",
    status,
    facts,
    model: {roles: {}, domains: {}, unsupported: {}},
  };
}

test("FACTS names the facts prove accepts", () => {
  // then: the request names match the Python tuple, including plural invariants
  assert.deepEqual(FACTS, ["choice", "invariants", "soundness", "refinement"]);
});

test("readProofReport accepts a version 1 document", () => {
  // given: one proved invariant fact
  const document = report([
    {
      fact: "invariant",
      subject: "place invariant 1",
      status: "proved",
      statement: "i + o = 1",
      findings: [],
    },
  ]);
  // when: the document is read
  const parsed = readProofReport(document);
  // then: the fact and the net are kept
  assert.equal(parsed.net, "sound");
  assert.equal(parsed.facts[0].fact, "invariant");
  assert.equal(parsed.source, "sound.petrinet");
});

test("readProofReport rejects a document that is not a report", () => {
  // when / then: a list is not a report
  assert.throws(() => readProofReport([]), ProofReportError);
  assert.throws(() => readProofReport({...report([]), version: 2}), ProofReportError);
  assert.throws(
    () => readProofReport(report([{fact: "invariants", subject: "x", status: "proved", statement: "x", findings: []}])),
    ProofReportError,
  );
});

test("proofReportStatus prefers refuted, then unknown", () => {
  // then: the rule matches the proof report
  assert.equal(proofReportStatus([{status: "proved"}, {status: "unknown"}]), "unknown");
  assert.equal(proofReportStatus([{status: "unknown"}, {status: "refuted"}]), "refuted");
  assert.equal(proofReportStatus([{status: "proved"}]), "proved");
  assert.equal(proofReportStatus([]), "proved");
});
