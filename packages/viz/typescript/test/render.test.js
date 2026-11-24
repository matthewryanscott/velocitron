import assert from "node:assert/strict";
import {describe, it} from "node:test";
import {
  ViewApplicationError,
  applyView,
  fusionCopy,
  fusionLayout,
  netRenderModel,
  netToDot,
  siblingGroups,
} from "../dist/index.js";

function featureNet() {
  return {
    name: "feature-net",
    places: [
      {name: "in_port", accepts: ["job"], port: {direction: "input", type: "job"}},
      {name: "out_port", accepts: ["job"], port: {direction: "output", type: "job"}},
      {name: "buffer", accepts: ["job", "flag"], description: "a buffer of jobs"},
    ],
    transitions: [
      {name: "work", handler: "work_handler"},
      {name: "gated", handler: "gated_handler", guard: "gate_guard", priority: 7},
    ],
    arcs: [
      {
        from: {place: "in_port"},
        to: {transition: "work"},
        consume: {type: "job", mode: "consume", weight: 2, predicate: {cel: 'kind == "batch"'}},
      },
      {
        from: {place: "buffer"},
        to: {transition: "work"},
        consume: {type: "flag", mode: "inhibit", weight: 1},
      },
      {
        from: {place: "buffer"},
        to: {transition: "gated"},
        consume: {type: "job", mode: "read", weight: 1, predicate: {handler: "job_ready"}},
      },
      {
        from: {transition: "work"},
        to: {place: "out_port"},
        produce: {type: "job", destination: "out_port", data: {fixed: true}},
      },
      {
        from: {transition: "gated"},
        to: {place: "buffer"},
        produce: {
          type: "flag",
          destination: "buffer",
          cel: '{"count": binding.buffer[0].count - 1}',
        },
      },
    ],
    initialMarking: {buffer: [{type: "job", data: {}}, {type: "job", data: {}}]},
  };
}

function choice(names, reads) {
  const places = [
    {name: "pending", accepts: ["job"]},
    {name: "switch", accepts: ["job"], annotations: {fusion: true}},
  ];
  const arcs = names.map((name) => ({
    from: {place: "pending"},
    to: {transition: name},
    consume: {type: "job", mode: "consume", weight: 1},
  }));
  for (const name of reads) {
    arcs.push({
      from: {place: "switch"},
      to: {transition: name},
      consume: {type: "job", mode: "read", weight: 1},
    });
  }
  return {
    name: "choice",
    places,
    transitions: names.map((name) => ({name})),
    arcs,
  };
}

const beside = {nodes: {"place:switch": {beside: true}}, arcs: {}, quietColors: [], shownFields: {}};

describe("net rendering", () => {
  it("draws ports, marks, guards, and arc modes", () => {
    // given: a net that exercises the structural drawing
    const net = featureNet();
    // when: the library renders it
    const dot = netToDot(net);
    const plain = netToDot(net, {style: {htmlLabels: false}});
    // then: the drawing names every feature the renderer distinguishes
    assert.ok(dot.includes("label=<<b>feature-net</b>>; labelloc=t;"));
    assert.ok(dot.includes("port input &#183; job"));
    assert.ok(dot.includes("port output &#183; job"));
    assert.equal(dot.split("peripheries=2").length - 1, 2);
    assert.ok(dot.includes("&#10216;job, flag&#10217;"));
    assert.ok(dot.includes("● × 2 job"));
    assert.ok(dot.includes("work_handler()"));
    assert.ok(dot.includes("guard: gate_guard?"));
    assert.ok(dot.includes("priority 7"));
    assert.ok(dot.includes("arrowhead=odot"));
    assert.ok(dot.includes("no flag"));
    assert.ok(dot.includes("read job"));
    assert.ok(dot.includes('color="#1f6feb", style=dashed'));
    assert.ok(dot.includes("2 &#215; job"));
    assert.ok(dot.includes('kind == "batch"'));
    assert.ok(dot.includes("pred: job_ready"));
    assert.ok(dot.includes('+ data {"fixed": true}'));
    assert.ok(dot.includes('+ data cel {"count": binding.buffer[0].count - 1}'));
    assert.equal(plain.includes("label=<"), false);
    assert.ok(plain.includes("⟨job, flag⟩"));
    assert.equal(netToDot(net, {includeMarking: false}).includes("●"), false);
  });

  it("draws one fusion copy per transition", () => {
    // given: one fusion place touched by three transitions
    const net = {
      name: "fusion-net",
      places: [
        {name: "window", accepts: ["tok"], annotations: {fusion: true}},
        {name: "src", accepts: ["job"]},
        {name: "dst", accepts: ["job"]},
      ],
      transitions: [
        {name: "open", handler: "open_h"},
        {name: "close", handler: "close_h"},
        {name: "idle", handler: "idle_h"},
      ],
      arcs: [
        {from: {place: "src"}, to: {transition: "open"}, consume: {type: "job", mode: "consume", weight: 1}},
        {from: {transition: "open"}, to: {place: "window"}, produce: {type: "tok", destination: "window"}},
        {from: {place: "window"}, to: {transition: "close"}, consume: {type: "tok", mode: "consume", weight: 1}},
        {from: {place: "window"}, to: {transition: "idle"}, consume: {type: "tok", mode: "inhibit", weight: 1}},
        {from: {transition: "close"}, to: {place: "dst"}, produce: {type: "job", destination: "dst"}},
      ],
      initialMarking: {window: [{type: "tok", data: {}}]},
    };
    // when: rendered with fusion copies, and again as one node
    const dot = netToDot(net);
    const flat = netToDot(net, {renderFusion: false});
    // then: each transition has a dashed local copy and the hub is absent
    assert.ok(dot.includes('"window@open"'));
    assert.ok(dot.includes('"window@close"'));
    assert.ok(dot.includes('"window@idle"'));
    assert.equal(dot.includes('"window" ['), false);
    assert.equal(dot.split('style=dashed, color="gray40"').length - 1, 3);
    assert.ok(dot.includes("<b>window</b>"));
    assert.ok(dot.includes('"open" -> "window@open"'));
    assert.ok(dot.includes("arrowhead=odot"));
    assert.equal(dot.split("● tok").length - 1, 3);
    assert.ok(flat.includes('"window" ['));
    assert.equal(flat.includes("window@"), false);
  });

  it("shares one fusion copy between neighbor siblings", () => {
    // given: a choice whose transitions also read one beside fusion place
    const pair = choice(["hold", "skip"], ["hold", "skip"]);
    const trio = choice(["hold", "skip", "send"], ["hold", "skip", "send"]);
    const fusion = new Set(["switch"]);
    // when: the layout places the copies
    const paired = fusionLayout(pair, fusion, beside);
    const three = fusionLayout(trio, fusion, beside);
    // then: two neighbors share the copy, and a run of three pairs from the left
    assert.deepEqual(siblingGroups(trio, fusion), [["hold", "skip", "send"]]);
    assert.equal(fusionCopy(paired, "switch", "hold"), "switch@hold+skip");
    assert.equal(fusionCopy(paired, "switch", "skip"), "switch@hold+skip");
    assert.deepEqual(paired.rows, [["hold", "switch@hold+skip", "skip"]]);
    assert.deepEqual(three.rows, [["hold", "switch@hold+skip", "skip", "send", "switch@send"]]);
    const dot = netToDot(pair, {decorations: beside});
    assert.ok(dot.includes('    "hold" -> "switch@hold+skip" -> "skip" [style=invis];'));
  });

  it("pins a view through the structural index", () => {
    // given: a rendered net and a view that positions one place
    const net = {
      name: "placed",
      places: [
        {name: "src", accepts: ["job"]},
        {name: "dst", accepts: ["job"]},
      ],
      transitions: [{name: "move", handler: "move"}],
      arcs: [
        {from: {place: "src"}, to: {transition: "move"}, consume: {type: "job", mode: "consume", weight: 1}},
        {from: {transition: "move"}, to: {place: "dst"}, produce: {type: "job", destination: "dst"}},
      ],
    };
    const model = netRenderModel(net);
    const raw = {
      annotations: {
        "petrinet.dsl/v1": {
          views: {wired: {positions: {"place:src": {x: 10, y: 20}}, routes: {}}},
          arcHandles: {},
        },
      },
    };
    // when: the view is applied
    const dot = applyView(model, raw, "wired");
    // then: the place is pinned and an unknown view is rejected
    assert.equal(model.dot, netToDot(net));
    assert.ok(dot.includes('pos="10,20!"'));
    assert.ok(dot.includes("layout=neato;"));
    assert.ok(dot.includes("splines=ortho;"));
    assert.throws(() => applyView(model, raw, "missing"), ViewApplicationError);
  });
});
