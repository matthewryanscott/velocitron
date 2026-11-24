import {execFileSync} from "node:child_process";
import {describe, expect, it} from "vitest";
import {domainViolation} from "@velocitron/engine";
import {parseNet} from "@velocitron/petrinet";
import {PYTHON} from "./python.mjs";

// ADR 0037: both engines word a domain violation the same way.

const PYTHON_VIOLATIONS = String.raw`
import json
import sys

from velocitron_engine import Token, domain_violation
from velocitron_petrinet import parse_net

net = parse_net(json.loads(sys.argv[1]))
tokens = json.loads(sys.argv[2])
print(json.dumps([domain_violation(net, "verdicts", Token(t["type"], t["data"])) for t in tokens]))
`;

const DOCUMENT = {
  name: "gate",
  places: [{name: "verdicts", accepts: ["verdict"]}],
  transitions: [],
  arcs: [],
  domains: {"verdict.result": ["pass", "hold"], "verdict.meta.level": [1, 2.5, true]},
};

describe("declared domain parity (ADR 0037)", () => {
  it("words every violation exactly as the Python engine does", () => {
    // given: tokens inside and outside the domains
    const tokens = [
      {type: "verdict", data: {result: "pass", meta: {level: 1.0}}},
      {type: "verdict", data: {result: "maybe", meta: {level: 1}}},
      {type: "verdict", data: {result: "pass"}},
      {type: "verdict", data: {result: "pass", meta: 3}},
      {type: "verdict", data: {result: "pass", meta: {level: false}}},
      {type: "verdict", data: {result: "pass", meta: {level: "1"}}},
      {type: "verdict", data: {result: "hold", meta: {level: 2.5}}},
    ];

    // when: both engines judge the same tokens
    const python = JSON.parse(
      execFileSync(
        PYTHON,
        ["-c", PYTHON_VIOLATIONS, JSON.stringify(DOCUMENT), JSON.stringify(tokens)],
        {encoding: "utf8"},
      ),
    );
    const net = parseNet(DOCUMENT);
    const typescript = tokens.map((token) => domainViolation(net, "verdicts", token));

    // then: they agree word for word
    expect(typescript).toEqual(python);
    expect(typescript[0]).toBeNull();
    expect(typescript[6]).toBeNull();
  });
});
