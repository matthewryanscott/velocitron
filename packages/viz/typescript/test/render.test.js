import assert from "node:assert/strict";
import {describe, it} from "node:test";
import {
  BESIDE_GAP,
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

  function lanes(positions) {
    return {
      annotations: {
        "petrinet.dsl/v1": {
          views: {lanes: {positions, routes: {}}},
          arcHandles: {},
        },
      },
    };
  }

  function nodeLine(dot, name) {
    const matches = dot.split("\n").filter((line) => line.startsWith(`    "${name}" [`));
    assert.equal(matches.length, 1, name);
    return matches[0];
  }

  function arc(from, to, kind) {
    if (kind === "produce") {
      return {
        from: {transition: from},
        to: {place: to.place},
        produce: {type: to.type, destination: to.place},
      };
    }
    return {
      from: {place: from},
      to: {transition: to},
      consume: {type: kind, mode: kind === "job" ? "consume" : "read", weight: 1},
    };
  }

  it("places each lease-lock copy beside its pinned transition", () => {
    // given: one fusion lock used by two workers, beside left, transitions pinned
    const places = [{name: "lock", accepts: ["permit"], annotations: {fusion: true}}];
    const transitions = [];
    const arcs = [];
    for (const worker of ["a", "b"]) {
      places.push(
        {name: `ready_${worker}`, accepts: ["job"]},
        {name: `held_${worker}`, accepts: ["job"]},
        {name: `done_${worker}`, accepts: ["job"]},
      );
      transitions.push({name: `acquire_${worker}`}, {name: `release_${worker}`});
      arcs.push(
        arc(`ready_${worker}`, `acquire_${worker}`, "job"),
        {
          from: {place: "lock"},
          to: {transition: `acquire_${worker}`},
          consume: {type: "permit", mode: "consume", weight: 1},
        },
        arc(`acquire_${worker}`, {place: `held_${worker}`, type: "job"}, "produce"),
        arc(`held_${worker}`, `release_${worker}`, "job"),
        arc(`release_${worker}`, {place: `done_${worker}`, type: "job"}, "produce"),
        arc(`release_${worker}`, {place: "lock", type: "permit"}, "produce"),
      );
    }
    const net = {name: "lease_lock", places, transitions, arcs};
    const decorations = {
      nodes: {"place:lock": {beside: true, besideSide: "left"}},
      arcs: {},
      quietColors: [],
      shownFields: {},
    };
    // when: the view is applied
    const dot = applyView(
      netRenderModel(net, {decorations}),
      lanes({
        "transition:acquire_a": {x: 0, y: 300},
        "transition:release_a": {x: 0, y: 100},
        "transition:acquire_b": {from: "transition:acquire_a", delta: {x: 300, y: 0}},
        "transition:release_b": {from: "transition:release_a", delta: {x: 300, y: 0}},
      }),
      "lanes",
    );
    // then: each copy sits one gap to the left of its own transition
    assert.ok(nodeLine(dot, "lock@acquire_a").includes(`pos="-${BESIDE_GAP},300!"`));
    assert.ok(nodeLine(dot, "lock@release_a").includes(`pos="-${BESIDE_GAP},100!"`));
    assert.ok(nodeLine(dot, "lock@acquire_b").includes(`pos="${300 - BESIDE_GAP},300!"`));
    assert.ok(nodeLine(dot, "lock@release_b").includes(`pos="${300 - BESIDE_GAP},100!"`));
    assert.ok(dot.includes("layout=neato;"));
    assert.equal(dot.includes("cluster_beside"), false);
    assert.equal(dot.includes("style=invis"), false);
  });

  it("steps copies on one side out by one gap", () => {
    // given: two left copies at one transition, switch first in arc order
    const net = {
      name: "stacked",
      places: [
        {name: "queued", accepts: ["job"]},
        {name: "switch", accepts: ["job"], annotations: {fusion: true}},
        {name: "budget", accepts: ["job"], annotations: {fusion: true}},
      ],
      transitions: [{name: "start"}],
      arcs: [
        arc("queued", "start", "job"),
        arc("switch", "start", "flag"),
        arc("budget", "start", "flag"),
      ],
    };
    const decorations = {
      nodes: {
        "place:switch": {beside: true, besideSide: "left"},
        "place:budget": {beside: true, besideSide: "left"},
      },
      arcs: {},
      quietColors: [],
      shownFields: {},
    };
    // when: the view pins start
    const dot = applyView(
      netRenderModel(net, {decorations}),
      lanes({"transition:start": {x: 0, y: 0}}),
      "lanes",
    );
    // then: the first copy is nearest, and the second is one gap farther
    assert.ok(nodeLine(dot, "switch@start").includes(`pos="-${BESIDE_GAP},0!"`));
    assert.ok(nodeLine(dot, "budget@start").includes(`pos="-${2 * BESIDE_GAP},0!"`));
  });

  it("places a shared beside copy between two pinned transitions", () => {
    // given: hold and skip share one beside copy
    const pair = choice(["hold", "skip"], ["hold", "skip"]);
    const model = netRenderModel(pair, {decorations: beside});
    // when: both transitions are pinned, and when only the left one is
    const both = applyView(
      model,
      lanes({
        "transition:hold": {x: 0, y: 0},
        "transition:skip": {x: 300, y: 0},
      }),
      "lanes",
    );
    const one = applyView(model, lanes({"transition:hold": {x: 0, y: 0}}), "lanes");
    // then: both pins put the copy at the midpoint, and one pin puts it one gap right
    assert.ok(nodeLine(both, "switch@hold+skip").includes('pos="150,0!"'));
    assert.ok(nodeLine(one, "switch@hold+skip").includes(`pos="${BESIDE_GAP},0!"`));
  });

  it("keeps a whole-place position on every fusion copy", () => {
    // given: the lease lock, with a position on the place as well as a transition
    const net = {
      name: "lease_lock",
      places: [
        {name: "lock", accepts: ["permit"], annotations: {fusion: true}},
        {name: "ready", accepts: ["job"]},
      ],
      transitions: [{name: "acquire"}, {name: "release"}],
      arcs: [
        arc("ready", "acquire", "job"),
        {
          from: {place: "lock"},
          to: {transition: "acquire"},
          consume: {type: "permit", mode: "consume", weight: 1},
        },
        arc("release", {place: "lock", type: "permit"}, "produce"),
      ],
    };
    const decorations = {
      nodes: {"place:lock": {beside: true, besideSide: "left"}},
      arcs: {},
      quietColors: [],
      shownFields: {},
    };
    // when: the view is applied
    const dot = applyView(
      netRenderModel(net, {decorations}),
      lanes({
        "transition:acquire": {x: 0, y: 0},
        "place:lock": {x: 10, y: 20},
      }),
      "lanes",
    );
    // then: every copy takes the place position
    assert.ok(nodeLine(dot, "lock@acquire").includes('pos="10,20!"'));
    assert.ok(nodeLine(dot, "lock@release").includes('pos="10,20!"'));
    assert.equal(dot.includes(`pos="-${BESIDE_GAP},0!"`), false);
  });
});
