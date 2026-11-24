import {execFileSync} from "node:child_process";
import {describe, expect, it} from "vitest";
import {Engine} from "@velocitron/runtime";
import {InMemoryJournal} from "@velocitron/journal";
import {HandlerRegistry} from "@velocitron/engine";
import {compilePetrinetText} from "@velocitron/petrinet";
import {lowerPetrinetText} from "@velocitron/dsl";
import {
  mergeComposition,
  mergeNets,
} from "@velocitron/petrinet";
import {parseComposition} from "@velocitron/petrinet";
import {parseNet} from "@velocitron/petrinet";
import {PYTHON} from "./python.mjs";

// CEL in a merged composition reads `binding` by the constituent's local
// place names (ADR 0032). Both ports must merge to the same binding names and
// fire the merged net the same way: correlate on a read arc, a correlated
// inhibit, a computed produce fallback, and a timer bound to a fused place.

const ORDERS = {
  name: "orders",
  places: [
    {name: "incoming", accepts: ["purchase"]},
    {name: "accepted", accepts: ["purchase"], port: {direction: "output", type: "purchase"}},
  ],
  transitions: [{name: "accept", handler: "noop"}],
  arcs: [
    {from: {place: "incoming"}, to: {transition: "accept"}, consume: {type: "purchase"}},
    {
      from: {transition: "accept"},
      to: {place: "accepted"},
      produce: {type: "purchase", destination: "accepted", cel: "binding.incoming[0]"},
    },
  ],
};

const SHIPPING = {
  name: "shipping",
  places: [
    {name: "inbox", accepts: ["purchase"], port: {direction: "input", type: "purchase"}},
    {name: "couriers", accepts: ["courier"]},
    {name: "holds", accepts: ["hold"]},
    {name: "clock", accepts: ["clock"]},
    {name: "receipts", accepts: ["receipt"]},
  ],
  transitions: [
    {
      name: "pack",
      handler: "noop",
      timer: {clock: "clock", cel: "clock.now >= request.due", bind: {request: "inbox"}},
    },
  ],
  arcs: [
    {from: {place: "inbox"}, to: {transition: "pack"}, consume: {type: "purchase"}},
    {
      from: {place: "couriers"},
      to: {transition: "pack"},
      consume: {
        type: "courier",
        mode: "read",
        correlate: {cel: "token.region == binding.inbox[0].region"},
      },
    },
    {
      from: {place: "holds"},
      to: {transition: "pack"},
      consume: {
        type: "hold",
        mode: "inhibit",
        correlate: {cel: "token.order == binding.inbox[0].id"},
      },
      description: "no hold on this order",
      annotations: {lane: "safety"},
    },
    {from: {place: "clock"}, to: {transition: "pack"}, consume: {type: "clock", mode: "read"}},
    {
      from: {transition: "pack"},
      to: {place: "receipts"},
      produce: {
        type: "receipt",
        destination: "receipts",
        cel: "{\"order\": binding.inbox[0].id, \"courier\": binding.couriers[0].name}",
      },
    },
  ],
};

const WIRES = [{from: {net: "orders", port: "accepted"}, to: {net: "shipping", port: "inbox"}}];

const MARKING = {
  "orders.incoming": [
    {type: "purchase", data: {id: "o-1", region: "eu", due: 5}},
    {type: "purchase", data: {id: "o-2", region: "us", due: 5}},
  ],
  "shipping.couriers": [
    {type: "courier", data: {region: "us", name: "sam"}},
    {type: "courier", data: {region: "eu", name: "eva"}},
  ],
  "shipping.holds": [{type: "hold", data: {order: "o-1"}}],
  "shipping.clock": [{type: "clock", data: {now: 10}}],
};

const SEQUENCE = ["orders.accept", "orders.accept", "shipping.pack"];

const PYTHON_TRACE = String.raw`
import dataclasses
import json
import sys
from collections.abc import Mapping, Sequence

from velocitron_engine import HandlerRegistry, Marking, Refinement, Token, Wire
from velocitron_petrinet import (
    compile_petrinet_text,
    merge_composition,
    merge_nets,
    parse_composition,
    parse_net,
)
from velocitron_runtime import Engine


def plain(value):
    if dataclasses.is_dataclass(value):
        return plain(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [plain(item) for item in value]
    return value


case = json.loads(sys.argv[1])
if "sources" in case:
    sources = case["sources"]
    net = merge_composition(
        parse_composition(
            compile_petrinet_text(sources[case["root"]], case["root"]),
            net_loader=lambda ref: compile_petrinet_text(sources[ref], ref),
        )
    )
else:
    net = merge_nets(
        {document["name"]: parse_net(document) for document in case["nets"]},
        [
            Wire(w["from"]["net"], w["from"]["port"], w["to"]["net"], w["to"]["port"])
            for w in case["wires"]
        ],
        [Refinement(**r) for r in case.get("refinements", [])],
    )
registry = HandlerRegistry()
registry.register_transition(
    "noop",
    lambda _: {"status": "completed", "outputTokens": {}, "error": None, "metadata": {}},
)
engine = Engine(registry, deposit_violation="raise")
marking = Marking(
    {
        place: [Token(t["type"], t["data"]) for t in tokens]
        for place, tokens in case["marking"].items()
    }
)
steps = []
for attempt, transition in enumerate(case["sequence"]):
    enabled = engine.enabled_transitions(net, marking, attempt=attempt)
    marking, record = engine.fire(net, marking, transition, attempt=attempt)
    record = plain(record)
    record.pop("timestamps", None)
    steps.append({
        "enabled": enabled,
        "record": record,
        "marking": {k: v for k, v in plain(marking).items() if v},
    })
print(json.dumps({
    "places": [[p.name, p.annotations] for p in net.places],
    "bindingNames": {t.name: t.binding_names for t in net.transitions},
    "arcs": [[a.description, a.annotations] for a in net.arcs],
    "steps": steps,
}))
`;

function pythonTrace(testCase) {
  return JSON.parse(execFileSync(PYTHON, [
    "-c",
    PYTHON_TRACE,
    JSON.stringify(testCase),
  ], {encoding: "utf8"}));
}

function typescriptNet(testCase) {
  if (testCase.sources !== undefined) {
    const compile = (ref) => compilePetrinetText(testCase.sources[ref], ref).document;
    const parsed = parseComposition(compile(testCase.root), {loadRef: compile});
    return mergeComposition(parsed.document, parsed.parsedNets);
  }
  return mergeNets(
    new Map(testCase.nets.map((document) => [document.name, parseNet(document)])),
    testCase.wires,
    testCase.refinements ?? [],
  );
}

function typescriptTrace(testCase) {
  const net = typescriptNet(testCase);
  const registry = new HandlerRegistry();
  registry.registerTransition("noop", () => ({
    status: "completed",
    outputTokens: {},
    error: null,
    metadata: {},
  }));
  const engine = new Engine(registry, {
    journal: new InMemoryJournal(),
    depositViolation: "raise",
    clock: {now: () => "excluded"},
  });
  let marking = testCase.marking;
  const steps = [];
  testCase.sequence.forEach((transition, attempt) => {
    const enabled = engine.enabledTransitions(net, marking, {attempt});
    const fired = engine.fire(net, marking, transition, {attempt});
    marking = fired.marking;
    const {timestamps: _excluded, ...record} = fired.record;
    steps.push({
      enabled,
      record,
      marking: Object.fromEntries(Object.entries(marking).filter(([, tokens]) => tokens.length > 0)),
    });
  });
  return {
    places: net.places.map((place) => [place.name, place.annotations ?? null]),
    bindingNames: Object.fromEntries(
      net.transitions.map((transition) => [transition.name, transition.bindingNames ?? null]),
    ),
    arcs: net.arcs.map((arc) => [arc.description ?? null, arc.annotations ?? null]),
    steps,
  };
}

describe("composition CEL names cross-language parity", () => {
  it("merges to the same binding names and fires the merged net the same way", () => {
    // given: two constituents whose CEL names their own local places
    const testCase = {nets: [ORDERS, SHIPPING], wires: WIRES, marking: MARKING, sequence: SEQUENCE};

    // when
    const python = pythonTrace(testCase);
    const typescript = typescriptTrace(testCase);

    // then: o-1 is held, so pack binds o-2 with the us courier
    expect(typescript).toEqual(python);
    expect(typescript.bindingNames["shipping.pack"]).toEqual({
      inbox: "orders.accepted",
      couriers: "shipping.couriers",
      clock: "shipping.clock",
    });
    expect(typescript.steps[2].record.status).toBe("completed");
    expect(typescript.steps[2].marking["shipping.receipts"]).toEqual([
      {type: "receipt", data: {order: "o-2", courier: "sam"}},
    ]);
  });
});

const SHOP = {
  name: "shop",
  places: [
    {name: "placed", accepts: ["parcel"]},
    {name: "sending", accepts: ["parcel"], port: {direction: "output", type: "parcel"}},
    {name: "delivered", accepts: ["receipt"], port: {direction: "input", type: "receipt"}},
    {name: "settled", accepts: ["receipt"]},
  ],
  transitions: [
    {name: "send", handler: "noop"},
    {name: "deliver", handler: "noop", annotations: {abstract: true}},
    {name: "settle", handler: "noop"},
  ],
  arcs: [
    {from: {place: "placed"}, to: {transition: "send"}, consume: {type: "parcel"}},
    {from: {transition: "send"}, to: {place: "sending"}, produce: {type: "parcel", destination: "sending", cel: "binding.placed[0]"}},
    {from: {place: "sending"}, to: {transition: "deliver"}, consume: {type: "parcel"}},
    {from: {transition: "deliver"}, to: {place: "delivered"}, produce: {type: "receipt", destination: "delivered", cel: "binding.sending[0]"}},
    {from: {place: "delivered"}, to: {transition: "settle"}, consume: {type: "receipt"}, description: "the receipt"},
    {from: {transition: "settle"}, to: {place: "settled"}, produce: {type: "receipt", destination: "settled", cel: "binding.delivered[0]"}},
  ],
};

const COURIER = {
  name: "courier",
  places: [
    {name: "pickup", accepts: ["parcel"], port: {direction: "input", type: "parcel"}},
    {name: "dropped", accepts: ["receipt"], port: {direction: "output", type: "receipt"}},
  ],
  transitions: [{name: "drop", handler: "noop"}],
  arcs: [
    {from: {place: "pickup"}, to: {transition: "drop"}, consume: {type: "parcel"}},
    {
      from: {transition: "drop"},
      to: {place: "dropped"},
      produce: {type: "receipt", destination: "dropped", cel: "{\"id\": binding.pickup[0].id}"},
      annotations: {lane: "courier"},
    },
  ],
};

describe("composition refinement cross-language parity", () => {
  it("removes the refined transition and fires the refining net the same way", () => {
    // given: the shop's abstract [deliver], refined by the courier net
    const testCase = {
      nets: [SHOP, COURIER],
      wires: [
        {from: {net: "shop", port: "sending"}, to: {net: "courier", port: "pickup"}},
        {from: {net: "courier", port: "dropped"}, to: {net: "shop", port: "delivered"}},
      ],
      refinements: [{net: "shop", transition: "deliver", by: "courier"}],
      marking: {"shop.placed": [{type: "parcel", data: {id: "p-1"}}]},
      sequence: ["shop.send", "courier.drop", "shop.settle"],
    };

    // when
    const python = pythonTrace(testCase);
    const typescript = typescriptTrace(testCase);

    // then: only the courier takes the sent parcel
    expect(typescript).toEqual(python);
    expect(Object.keys(typescript.bindingNames)).toEqual([
      "shop.send",
      "shop.settle",
      "courier.drop",
    ]);
    expect(typescript.steps[1].enabled).toEqual(["courier.drop"]);
    expect(typescript.steps[2].marking["shop.settled"]).toEqual([
      {type: "receipt", data: {id: "p-1"}},
    ]);
  });
});

// A lock shared by two nets (ADR 0040), used as one constituent of an outer
// composition (ADR 0041) whose worker refines the pair's abstract [work].
const LOCK_SOURCES = {
  "take.petrinet": `net take "Start a job when the lock is free"
(todo) -job-> [take]
@started: [take] -job-> (busy)
@started data cel "binding.todo[0]"
@lock_in: (lock) -key-> [take]
(lock) annotation fusion true
(busy) port output job
[take] handler "noop"
`,
  "give.petrinet": `net give "Work the job, end it and give the lock back"
(busy) -job-> [work] -job-> (worked)
(worked) -job-> [give]
@ended: [give] -job-> (done)
@ended data cel "binding.worked[0]"
@unlock: [give] -key-> (lock)
@unlock data {}
(busy) port input job
(worked) port input job
(done) port output job
[work] handler "noop"
[give] handler "noop"
`,
  "pair/pair.petrinet": `composition pair
use "../take.petrinet" as take
use "../give.petrinet" as give
wire take.(busy) -> give.(busy)
share take.(lock) ~ give.(lock)
`,
  "worker.petrinet": `net worker "The work, in detail"
(start) -job-> [do]
@did: [do] -job-> (end)
@did data cel "binding.start[0]"
(start) port input job
(end) port output job
[do] handler "noop"
`,
  "nested.petrinet": `composition nested
use "pair/pair.petrinet" as pair
use "worker.petrinet" as worker
wire pair.(take.busy) -> worker.(start)
wire worker.(end) -> pair.(give.worked)
refine pair.[give.work] by worker
`,
};

describe("composition share and nesting cross-language parity", () => {
  it("flattens, shares the lock, and fires the merged net the same way", () => {
    // given: one job and a free lock
    const testCase = {
      sources: LOCK_SOURCES,
      root: "nested.petrinet",
      marking: {
        "pair.take.todo": [{type: "job", data: {id: 1}}, {type: "job", data: {id: 2}}],
        "pair.give.lock__pair.take.lock": [{type: "key", data: {}}],
      },
      sequence: ["pair.take.take", "worker.do", "pair.give.give", "pair.take.take"],
    };

    // when
    const python = pythonTrace(testCase);
    const typescript = typescriptTrace(testCase);

    // then: the second job waits until the first gives the lock back
    expect(typescript).toEqual(python);
    expect(typescript.steps[0].enabled).toEqual(["pair.take.take"]);
    expect(typescript.steps[1].enabled).toEqual(["worker.do"]);
    expect(typescript.steps[3].marking["pair.give.lock__pair.take.lock"]).toBeUndefined();
    expect(typescript.places).toContainEqual(["pair.give.lock__pair.take.lock", {fusion: true}]);
  });

  it("lowers and compiles `share` and dotted paths to the same IR and JSON", () => {
    // given: a three-way share and the nested composition's dotted endpoints
    const sources = {
      "share.petrinet":
        'composition shared\nuse "a.petrinet" as a\nuse "b.petrinet" as b\nuse "c.petrinet" as c\n' +
        "share a.(lock) ~ b.(\"the lock\") ~ c.(lock)\nshare a.(lock) ~ b.(\"the lock\") ~ c.(lock)\n",
      "nested.petrinet": LOCK_SOURCES["nested.petrinet"],
    };

    // when
    const python = JSON.parse(execFileSync(PYTHON, ["-c", PYTHON_LOWER, JSON.stringify(sources)], {encoding: "utf8"}));
    const typescript = Object.fromEntries(
      Object.entries(sources).map(([sourceId, text]) => [
        sourceId,
        {ir: lowerPetrinetText(text, sourceId), document: compilePetrinetText(text, sourceId).document},
      ]),
    );

    // then
    expect(typescript).toEqual(python);
    expect(typescript["share.petrinet"].document.shares).toEqual([
      {places: [{net: "a", place: "lock"}, {net: "b", place: "the lock"}, {net: "c", place: "lock"}]},
    ]);
  });
});

const PYTHON_LOWER = String.raw`
import json
import sys

from velocitron_dsl import lower_petrinet_text
from velocitron_petrinet import compile_petrinet_text

print(json.dumps({
    source_id: {
        "ir": lower_petrinet_text(text, source_id),
        "document": compile_petrinet_text(text, source_id),
    }
    for source_id, text in json.loads(sys.argv[1]).items()
}))
`;

describe("merged net DSL round trip", () => {
  it("writes binding names as bind facts that both ports read back", () => {
    // given: the merged shop, which carries binding names and arc documentation
    const merged = JSON.parse(JSON.stringify(typescriptNet({nets: [ORDERS, SHIPPING], wires: WIRES})));

    // when: Python writes it as .petrinet and both ports compile that text
    const python = JSON.parse(
      execFileSync(PYTHON, ["-c", PYTHON_ROUND_TRIP, JSON.stringify(merged)], {
        encoding: "utf8",
      }),
    );
    const typescript = compilePetrinetText(python.petrinet, "merged.petrinet").document;

    // then: the net comes back unchanged beside the compiler's DSL payload
    expect(python.petrinet).toContain('["shipping.pack"] bind inbox ("orders.accepted")');
    const {annotations, ...roundTripped} = JSON.parse(JSON.stringify(parseNet(python.document)));
    expect(Object.keys(annotations)).toEqual(["petrinet.dsl/v1"]);
    expect(roundTripped).toEqual({...merged, initialMarking: {}});
    expect(typescript).toEqual(python.document);
  });
});

const PYTHON_ROUND_TRIP = String.raw`
import json
import sys

from velocitron_dsl import emit_petrinet
from velocitron_petrinet import compile_petrinet_text

petrinet = emit_petrinet(json.loads(sys.argv[1]))
print(json.dumps({"petrinet": petrinet, "document": compile_petrinet_text(petrinet)}))
`;
