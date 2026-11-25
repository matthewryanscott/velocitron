import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {readFileSync} from "node:fs";
import {dirname, join} from "node:path";
import {describe, it} from "node:test";
import {fileURLToPath} from "node:url";
import {
  NAME_POINT,
  SMALL_POINT,
  ViewApplicationError,
  applyView,
  besideGap,
  nodeWidth,
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

  function coord(value) {
    return Number.isInteger(value) ? String(value) : String(value);
  }

  function placeWidth(name, color) {
    return nodeWidth([[name, NAME_POINT], [`⟨${color}⟩`, SMALL_POINT]]);
  }

  function transitionWidth(name) {
    return nodeWidth([[name, NAME_POINT]]);
  }

  function gap(transition, place, color) {
    return besideGap(transitionWidth(transition), placeWidth(place, color));
  }

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
    const lockGap = gap("acquire_a", "lock", "permit");
    assert.ok(nodeLine(dot, "lock@acquire_a").includes(`pos="-${coord(lockGap)},300!"`));
    assert.ok(nodeLine(dot, "lock@release_a").includes(`pos="-${coord(lockGap)},100!"`));
    assert.ok(nodeLine(dot, "lock@acquire_b").includes(`pos="${coord(300 - lockGap)},300!"`));
    assert.ok(nodeLine(dot, "lock@release_b").includes(`pos="${coord(300 - lockGap)},100!"`));
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
    const step = gap("start", "switch", "job");
    assert.ok(nodeLine(dot, "switch@start").includes(`pos="-${coord(step)},0!"`));
    assert.ok(nodeLine(dot, "budget@start").includes(`pos="-${coord(2 * step)},0!"`));
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
    assert.ok(nodeLine(one, "switch@hold+skip").includes(`pos="${coord(gap("hold", "switch", "job"))},0!"`));
  });

  it("places the beside conformance net the way lanes and lanes_lock ask", () => {
    // given: the 20-decoration-beside net, with a pinned view and a lanes_lock view
    const net = {
      name: "beside",
      places: [
        {name: "queued", accepts: ["job"]},
        {name: "running", accepts: ["job"]},
        {name: "done", accepts: ["job"]},
        {name: "switch", accepts: ["flag"], annotations: {fusion: true}},
        {name: "budget", accepts: ["credit"], annotations: {fusion: true}},
      ],
      transitions: [{name: "start"}, {name: "finish"}],
      arcs: [
        arc("queued", "start", "job"),
        arc("start", {place: "running", type: "job"}, "produce"),
        arc("running", "finish", "job"),
        arc("finish", {place: "done", type: "job"}, "produce"),
        arc("switch", "start", "flag"),
        arc("switch", "finish", "flag"),
        arc("budget", "start", "flag"),
      ],
    };
    const decorations = {
      nodes: {
        "place:switch": {beside: true, besideSide: "left"},
        "place:budget": {beside: true},
      },
      arcs: {},
      quietColors: [],
      shownFields: {},
    };
    const model = netRenderModel(net, {decorations});
    const start = gap("start", "switch", "flag");
    const finish = gap("finish", "switch", "flag");
    const budget = gap("start", "budget", "credit");
    // when: lanes pins the transitions
    const lanesDot = applyView(
      model,
      lanes({
        "transition:start": {x: 0, y: 200},
        "transition:finish": {from: "transition:start", delta: {x: 0, y: -200}},
      }),
      "lanes",
    );
    // then: switch is left of each transition and budget is right of start
    assert.ok(nodeLine(lanesDot, "switch@start").includes(`pos="-${coord(start)},200!"`));
    assert.ok(nodeLine(lanesDot, "switch@finish").includes(`pos="-${coord(finish)},0!"`));
    assert.ok(nodeLine(lanesDot, "budget@start").includes(`pos="${coord(budget)},200!"`));
    assert.ok(lanesDot.includes("constraint=false"));
    // when: lanes_lock also positions switch, and done is relative to it
    const locked = applyView(
      model,
      lanes({
        "transition:start": {x: 0, y: 200},
        "transition:finish": {from: "transition:start", delta: {x: 0, y: -200}},
        "place:switch": {x: 40, y: 0},
        "place:done": {from: "place:switch", delta: {x: 80, y: 0}},
      }),
      "lanes",
    );
    // then: the place point lands on each switch copy, and done uses that anchor
    assert.ok(nodeLine(locked, "switch@start").includes('pos="40,0!"'));
    assert.ok(nodeLine(locked, "switch@finish").includes('pos="40,0!"'));
    assert.ok(nodeLine(locked, "done").includes('pos="120,0!"'));
    // and: budget has no place position, so beside still places it
    assert.ok(nodeLine(locked, "budget@start").includes(`pos="${coord(budget)},200!"`));
  });

  it("lets a whole-place position beat beside and anchor relative", () => {
    // given: a fusion lock with beside, a place position, and one pinned transition
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
        "place:ready": {from: "place:lock", delta: {x: 10, y: 0}},
      }),
      "lanes",
    );
    // then: both copies take the place point, and ready uses that anchor
    assert.ok(nodeLine(dot, "lock@acquire").includes('pos="10,20!"'));
    assert.ok(nodeLine(dot, "lock@release").includes('pos="10,20!"'));
    assert.ok(nodeLine(dot, "ready").includes('pos="20,20!"'));
  });

  it("lets a copy position beat the place, which beats beside", () => {
    // given: beside lock, a place position, one copy position, and a relative base
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
    const decorations = {
      nodes: {"place:lock": {beside: true, besideSide: "left"}},
      arcs: {},
      quietColors: [],
      shownFields: {},
    };
    const model = netRenderModel(
      {name: "lease_lock", places, transitions, arcs},
      {decorations},
    );
    // when: the view is applied
    const dot = applyView(
      model,
      lanes({
        "transition:acquire_a": {x: 0, y: 0},
        "transition:release_a": {x: 200, y: 0},
        "place:lock": {x: 10, y: 20},
        "place:lock@transition:acquire_a": {
          from: "transition:acquire_a",
          delta: {x: -70, y: 0},
        },
        "place:ready_a": {
          from: "place:lock@transition:acquire_a",
          delta: {x: 5, y: 0},
        },
      }),
      "lanes",
    );
    // then: the copy entry wins, the other copy takes the place, and ready_a
    // sits on the copy's rendered point
    assert.notEqual(
      model.copyLines.get("lock\0acquire_a"),
      model.copyLines.get("lock\0release_a"),
    );
    assert.ok(nodeLine(dot, "lock@acquire_a").includes('pos="-70,0!"'));
    assert.ok(nodeLine(dot, "lock@release_a").includes('pos="10,20!"'));
    assert.ok(nodeLine(dot, "ready_a").includes('pos="-65,0!"'));
  });

  it("places a shared copy from its one agreed entry", () => {
    // given: hold and skip share one beside copy
    const pair = choice(["hold", "skip"], ["hold", "skip"]);
    const model = netRenderModel(pair, {decorations: beside});
    // when: both names of the shared copy carry the same point
    const dot = applyView(
      model,
      lanes({
        "transition:hold": {x: 0, y: 0},
        "transition:skip": {x: 300, y: 0},
        "place:switch": {x: 10, y: 10},
        "place:switch@transition:hold": {x: 40, y: 80},
        "place:switch@transition:skip": {x: 40, y: 80},
        "place:pending": {
          from: "place:switch@transition:skip",
          delta: {x: 0, y: -10},
        },
      }),
      "lanes",
    );
    // then: one line, the agreed point, and pending uses that rendered point
    assert.equal(model.copyLines.get("switch\0hold"), model.copyLines.get("switch\0skip"));
    assert.ok(nodeLine(dot, "switch@hold+skip").includes('pos="40,80!"'));
    assert.equal(nodeLine(dot, "switch@hold+skip").includes('pos="150,0!"'), false);
    assert.ok(nodeLine(dot, "pending").includes('pos="40,70!"'));
    assert.throws(
      () =>
        applyView(
          model,
          lanes({
            "place:switch@transition:hold": {x: 1, y: 1},
            "place:switch@transition:skip": {x: 2, y: 2},
          }),
          "lanes",
        ),
      (error) => error instanceof ViewApplicationError && /shared copy of place 'switch'/.test(error.message),
    );
  });

  function sixLock() {
    const places = [{name: "lock", accepts: ["permit"], annotations: {fusion: true}}];
    const transitions = [];
    const arcs = [];
    for (const worker of ["a", "b", "c"]) {
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
    return {name: "lease_lock", places, transitions, arcs};
  }

  function sixPositions() {
    const positions = {"place:lock": {x: 9999, y: 9999}};
    for (const [index, worker] of ["a", "b", "c"].entries()) {
      const origin = index * 640;
      positions[`transition:acquire_${worker}`] = {x: origin, y: 560};
      positions[`transition:release_${worker}`] = {x: origin, y: 0};
      positions[`place:lock@transition:acquire_${worker}`] = {x: origin - 220, y: 560};
      positions[`place:lock@transition:release_${worker}`] = {x: origin - 220, y: 0};
      positions[`place:held_${worker}`] = {x: origin, y: 280};
      positions[`place:done_${worker}`] = {x: origin, y: -280};
      if (worker === "a") {
        positions["place:ready_a"] = {
          from: "place:lock@transition:acquire_a",
          delta: {x: 0, y: 280},
        };
      } else {
        positions[`place:ready_${worker}`] = {x: origin, y: 840};
      }
    }
    return positions;
  }

  it("pins six lock copies without stacking or scaling", () => {
    // given: three workers and a position for every copy
    const decorations = {
      nodes: {"place:lock": {beside: true, besideSide: "left"}},
      arcs: {},
      quietColors: [],
      shownFields: {},
    };
    const dot = applyView(
      netRenderModel(sixLock(), {decorations}),
      lanes(sixPositions()),
      "lanes",
    );
    const copies = ["a", "b", "c"].flatMap((worker) => [
      `lock@acquire_${worker}`,
      `lock@release_${worker}`,
    ]);
    // when: the golden is read, and neato lays the drawing out
    const golden = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../../fixtures/lease-lock-six-copies.dot"),
      "utf8",
    );
    const points = copies.map((name) => {
      const line = nodeLine(dot, name);
      const start = line.indexOf('pos="') + 5;
      return line.slice(start, line.indexOf("!", start));
    });
    const plain = execFileSync("dot", ["-Tplain"], {input: dot, encoding: "utf8"});
    const header = plain.split("\n")[0].split(" ");
    const found = new Map();
    for (const line of plain.split("\n")) {
      const parts = line.split(" ");
      if (parts[0] === "node") {
        found.set(parts[1].replaceAll('"', ""), [Number(parts[2]), Number(parts[3])]);
      }
    }
    // then: the drawing matches Python, no two copies share a point, and
    // overlap=scale leaves the pins. Plain coordinates are shifted to the
    // layout corner; the distances between copies stay the authored ones.
    assert.equal(dot, golden);
    assert.equal(new Set(points).size, 6);
    assert.equal(dot.includes("9999,9999"), false);
    assert.ok(nodeLine(dot, "ready_a").includes('pos="-220,840!"'));
    assert.equal(Number(header[1]), 1);
    const anchor = found.get("lock@acquire_a");
    assert.ok(anchor);
    const shift = [anchor[0] - (-220 / 72), anchor[1] - (560 / 72)];
    for (const [index, worker] of ["a", "b", "c"].entries()) {
      const origin = index * 640;
      for (const [name, point] of [
        [`lock@acquire_${worker}`, [origin - 220, 560]],
        [`lock@release_${worker}`, [origin - 220, 0]],
      ]) {
        const node = found.get(name);
        assert.ok(node, name);
        assert.ok(Math.abs(node[0] - (point[0] / 72 + shift[0])) < 0.02, name);
        assert.ok(Math.abs(node[1] - (point[1] / 72 + shift[1])) < 0.02, name);
      }
    }
    const ready = found.get("ready_a");
    const copy = found.get("lock@acquire_a");
    assert.ok(ready && copy);
    assert.ok(Math.abs(ready[1] - copy[1] - 280 / 72) < 0.02);
  });
});
