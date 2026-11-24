import {NetValidationError} from "./errors.js";
import type {
  Arc,
  CompositionDocument,
  CompositionPlaceEndpoint,
  CompositionRefinement,
  CompositionShare,
  DeclaredInvariant,
  ProofFacts,
  CompositionWire,
  JsonValue,
  Net,
  Place,
  Port,
  ReadonlyJsonObject,
  Timer,
  Token,
  Transition,
} from "./types.js";

/**
 * The runtime composition merge engine — a browser-safe port of the Python
 * reference implementation (`implementations/python/src/velocitron/composition.py`;
 * spec `spec/composition.md`; ADR 0004).
 *
 * Produces the combined {@link Net} from nets keyed by alias plus a list of
 * wires: alias-qualifies every place/transition/arc endpoint, fuses wired
 * port-places into single shared places (place-fusion realization), rewrites
 * arc endpoints and produce destinations, and re-exposes unwired ports as the
 * composition's own boundary ports. The output is one {@link Net}, verifiable
 * as a single Petri net and runnable by the `Engine`.
 *
 * Pure data transform — no fs/path/process; safe under the browser seam audit.
 *
 * This module is the source of truth for the transform. It does not
 * re-validate the merged net and does not import `@velocitron/core`.
 * The umbrella calls it and then revalidates.
 */

/** Minimal union-find over port-place qualified names (N-ary fusion). */
class UnionFind {
  private readonly parent: Map<string, string>;

  constructor(names: Iterable<string>) {
    this.parent = new Map();
    for (const name of names) this.parent.set(name, name);
  }

  find(name: string): string {
    let root = name;
    while (this.parent.get(root) !== root) root = this.parent.get(root) as string;
    // Path compression.
    let current = name;
    while (this.parent.get(current) !== root) {
      const next = this.parent.get(current) as string;
      this.parent.set(current, root);
      current = next;
    }
    return root;
  }

  union(a: string, b: string): void {
    const ra = this.find(a);
    const rb = this.find(b);
    if (ra !== rb) this.parent.set(ra, rb);
  }
}

/**
 * Apply `rename` to a timer's place references (clock + bind values). The CEL
 * string is never touched — it references only the reserved `clock` variable
 * and the `bind` aliases, which is what makes a timed transition
 * composition-safe (ADR 0018): the merge rewrites the place *values* exactly as
 * it rewrites arc endpoints, and the expression survives.
 */
function mapTimerPlaces(timer: Timer, rename: (place: string) => string): Timer {
  return {
    clock: rename(timer.clock),
    cel: timer.cel,
    ...(timer.bind === undefined
      ? {}
      : {
          bind: Object.fromEntries(
            Object.entries(timer.bind).map(([variable, place]) => [
              variable,
              rename(place),
            ]),
          ),
        }),
    ...(timer.maturity === undefined ? {} : {maturity: timer.maturity}),
  };
}

/**
 * A fused class's members in the order they win conflicts
 * (spec/composition.md "Fused-place annotations").
 *
 * Output (source) ports come before input ports — the fused place is named
 * after its sources, and they take the same precedence — each group in
 * sorted qualified-name order.
 */
function memberPrecedence(
  members: readonly string[],
  qnameToPlace: ReadonlyMap<string, Place>,
): string[] {
  const isOutput = (name: string): boolean => {
    const port = (qnameToPlace.get(name) as Place).port;
    return port !== undefined && port.direction === "output";
  };
  return [
    ...members.filter(isOutput).sort(),
    ...members.filter((member) => !isOutput(member)).sort(),
  ];
}

/** The first member's description, in precedence order. */
function fusedDescription(
  ordered: readonly string[],
  qnameToPlace: ReadonlyMap<string, Place>,
): string | undefined {
  for (const member of ordered) {
    const description = (qnameToPlace.get(member) as Place).description;
    if (description) return description;
  }
  return undefined;
}

/**
 * Annotations for a fused place: the members' annotations, the earliest
 * member in precedence order winning conflicting keys. The `fusion: true`
 * tag is set last, overriding any member value, so the viz renderer's
 * fusion-place styling triggers on every fused place.
 */
function fusedAnnotations(
  ordered: readonly string[],
  qnameToPlace: ReadonlyMap<string, Place>,
): ReadonlyJsonObject {
  const annotations: Record<string, JsonValue> = {};
  for (const member of ordered) {
    const memberAnnotations = (qnameToPlace.get(member) as Place).annotations;
    if (memberAnnotations === undefined) continue;
    for (const [key, value] of Object.entries(memberAnnotations)) {
      if (!(key in annotations)) annotations[key] = value;
    }
  }
  annotations.fusion = true;
  return annotations;
}

type DomainValues = readonly (boolean | number | string)[];

/** Every constituent's domains; a color field keeps one value set (ADR 0037). */
function mergedDomains(aliasToNet: ReadonlyMap<string, Net>): Record<string, DomainValues> {
  const merged: Record<string, DomainValues> = {};
  const owner = new Map<string, string>();
  const valueSet = (values: DomainValues): string =>
    values.map((value) => JSON.stringify(value)).sort().join("\n");
  for (const [alias, net] of aliasToNet) {
    for (const [key, values] of Object.entries(net.domains ?? {})) {
      const first = owner.get(key);
      if (first === undefined) {
        merged[key] = [...values];
        owner.set(key, alias);
      } else if (valueSet(merged[key] as DomainValues) !== valueSet(values)) {
        throw new NetValidationError([
          {
            code: "composition.domain_conflict",
            path: "/nets",
            message: `domain ${key} differs between ${first} and ${alias}`,
            details: {domain: key, nets: [first, alias]},
          },
        ]);
      }
    }
  }
  return merged;
}

/**
 * Constituents' proof facts under merged place names (ADR 0037). A declared
 * invariant keeps its weights (a fused place sums its members' weights). The
 * composition's own final markings replace its nets' final places (ADR 0049).
 * Without them, a net's final marking stays final only while no arc of the
 * composition reads or takes from its places.
 */
function mergedProofs(
  aliasToNet: ReadonlyMap<string, Net>,
  rewrite: (name: string) => string,
  arcs: readonly Arc[],
  compositionFinal?: readonly (readonly CompositionPlaceEndpoint[])[],
): ProofFacts | undefined {
  const read = new Set(
    arcs.flatMap((arc) => (arc.consume !== undefined ? [arc.from.place] : [])),
  );
  const final: string[][] = [];
  const add = (marking: readonly string[]): void => {
    const places = [...new Set(marking)];
    const same = (known: string[]): boolean =>
      known.length === places.length && places.every((place) => known.includes(place));
    if (!final.some(same)) final.push(places);
  };
  for (const marking of compositionFinal ?? []) {
    add(marking.map((member) => rewrite(`${member.net}.${member.place}`)));
  }
  const invariants: DeclaredInvariant[] = [];
  let declared = compositionFinal !== undefined;
  for (const [alias, net] of aliasToNet) {
    if (net.proofs === undefined) continue;
    declared = true;
    if (compositionFinal === undefined) {
      for (const entry of net.proofs.final ?? []) {
        const places = (typeof entry === "string" ? [entry] : entry).map((place) =>
          rewrite(`${alias}.${place}`),
        );
        if (!places.some((place) => read.has(place))) add(places);
      }
    }
    for (const invariant of net.proofs.invariants ?? []) {
      const weights: Record<string, number> = {};
      for (const [place, weight] of Object.entries(invariant.weights)) {
        const name = rewrite(`${alias}.${place}`);
        weights[name] = (weights[name] ?? 0) + weight;
      }
      invariants.push({
        weights,
        ...(invariant.constant === undefined ? {} : {constant: invariant.constant}),
        ...(invariant.name === undefined ? {} : {name: `${alias}.${invariant.name}`}),
      });
    }
  }
  if (!declared) return undefined;
  return {
    ...(final.length === 0
      ? {}
      : {final: final.map((places) => (places.length === 1 ? places[0]! : places))}),
    ...(invariants.length === 0 ? {} : {invariants}),
  };
}

/** A transition's annotations with its net's default actor filled in. */
function withActor(
  annotations: ReadonlyJsonObject | undefined,
  defaultActor: JsonValue | undefined,
): ReadonlyJsonObject | undefined {
  if (typeof defaultActor !== "string" || Object.hasOwn(annotations ?? {}, "actor")) {
    return annotations;
  }
  return {...annotations, actor: defaultActor};
}

interface DeclaredActor {
  readonly name: string;
  readonly kind: string;
}

/** Every constituent's declared actors, first declaration first (ADR 0038). */
function mergedActors(aliasToNet: ReadonlyMap<string, Net>): DeclaredActor[] {
  const merged = new Map<string, string>();
  for (const [alias, net] of aliasToNet) {
    const declared = net.annotations?.actors;
    if (!Array.isArray(declared)) continue;
    for (const entry of declared as readonly JsonValue[]) {
      if (entry === null || typeof entry !== "object" || Array.isArray(entry)) continue;
      const {name, kind = "system"} = entry as ReadonlyJsonObject;
      if (typeof name !== "string") continue;
      const first = merged.get(name);
      if (first !== undefined && first !== kind) {
        throw new NetValidationError([
          {
            code: "composition.actor_conflict",
            path: "/nets",
            message: `actor ${name} is a ${first} in one net and a ${String(kind)} in ${alias}`,
            details: {actor: name, net: alias},
          },
        ]);
      }
      if (first === undefined) merged.set(name, kind as string);
    }
  }
  return [...merged].map(([name, kind]) => ({name, kind}));
}

/** A port facet on the place of this name, when that place declares one. */
export function findPort(net: Net, portName: string): Port | undefined {
  // Ports are place facets: a port exists iff a place of that name declares one.
  for (const place of net.places) {
    if (place.name === portName) return place.port;
  }
  return undefined;
}

/**
 * Checks that each refining net fits the transition it replaces.
 *
 * Every place the transition consumes from or reads must be wired (directly
 * or through a fused class) to an input port of the refining net with the
 * arc's color, and every place it produces into must be wired from an output
 * port of the refining net with that color. Inhibit arcs and timers are
 * rejected: no port direction carries a test for absence or a clock. The
 * messages match the Python `_validate_refinements`.
 */
export function validateRefinements(
  refinements: readonly CompositionRefinement[],
  wires: readonly CompositionWire[],
  aliasToNet: ReadonlyMap<string, Net>,
  shares: readonly CompositionShare[] = [],
): void {
  const neighbors = new Map<string, Set<string>>();
  const link = (a: string, b: string): void => {
    const set = neighbors.get(a) ?? new Set<string>();
    set.add(b);
    neighbors.set(a, set);
  };
  for (const wire of wires) {
    const source = `${wire.from.net}.${wire.from.port}`;
    const sink = `${wire.to.net}.${wire.to.port}`;
    link(source, sink);
    link(sink, source);
  }
  for (const share of shares) {
    const names = share.places.map((member) => `${member.net}.${member.place}`);
    for (const name of names) {
      for (const other of names) link(name, other);
    }
  }
  const fusedWith = (qualifiedPlace: string): Set<string> => {
    const members = new Set([qualifiedPlace]);
    const pending = [qualifiedPlace];
    while (pending.length > 0) {
      for (const neighbor of neighbors.get(pending.pop() as string) ?? []) {
        if (!members.has(neighbor)) {
          members.add(neighbor);
          pending.push(neighbor);
        }
      }
    }
    return members;
  };

  const refinedBy = new Map<string, string>();
  for (const [index, refinement] of refinements.entries()) {
    const {net: netAlias, transition: name, by} = refinement;
    const path = `/refinements/${index}`;
    const prefix = `refine ${netAlias}.[${name}] by ${by}: `;
    for (const alias of [netAlias, by]) {
      if (!aliasToNet.has(alias)) {
        throw new NetValidationError([{code: "composition.refinement.alias_unknown", path, message: `${prefix}unknown alias ${alias}`}]);
      }
    }
    if (by === netAlias) {
      throw new NetValidationError([{code: "composition.refinement.self", path, message: `${prefix}a net cannot refine its own transition`}]);
    }
    const key = JSON.stringify([netAlias, name]);
    const earlier = refinedBy.get(key);
    if (earlier !== undefined) {
      throw new NetValidationError([{code: "composition.refinement.duplicate", path, message: `${prefix}${netAlias}.[${name}] is already refined by ${earlier}`}]);
    }
    refinedBy.set(key, by);
    const net = aliasToNet.get(netAlias) as Net;
    const transition = net.transitions.find((candidate) => candidate.name === name);
    if (transition === undefined) {
      throw new NetValidationError([{code: "composition.refinement.transition_unknown", path, message: `${prefix}net ${netAlias} has no transition [${name}]`}]);
    }
    if (transition.timer !== undefined) {
      throw new NetValidationError([{code: "composition.refinement.unsupported", path, message: `${prefix}[${name}] has a timer; a refined transition may only consume, read and produce`}]);
    }
    const subnet = aliasToNet.get(by) as Net;
    for (const arc of net.arcs) {
      let place: string;
      let color: string;
      let direction: Port["direction"];
      let flow: string;
      let linkText: string;
      if (arc.consume !== undefined && arc.to.transition === name) {
        place = arc.from.place;
        color = arc.consume.type;
        if (arc.consume.mode === "inhibit") {
          throw new NetValidationError([{code: "composition.refinement.unsupported", path, message: `${prefix}[${name}] has an inhibit arc from (${place}); a refined transition may only consume, read and produce`}]);
        }
        direction = "input";
        flow = `takes ${color} from (${place})`;
        linkText = "to an input port of";
      } else if (arc.produce !== undefined && arc.from.transition === name) {
        place = arc.to.place;
        color = arc.produce.type;
        direction = "output";
        flow = `gives ${color} to (${place})`;
        linkText = "from an output port of";
      } else {
        continue;
      }
      const portTypes = new Set<string>();
      for (const member of fusedWith(`${netAlias}.${place}`)) {
        // Aliases of nets inside a nested composition hold dots, so match
        // the refining alias as a prefix rather than splitting at a dot.
        if (!member.startsWith(`${by}.`)) continue;
        const port = findPort(subnet, member.slice(by.length + 1));
        if (port !== undefined && port.direction === direction) portTypes.add(port.type);
      }
      if (portTypes.has(color)) continue;
      if (portTypes.size === 0) {
        throw new NetValidationError([{code: "composition.refinement.unfit", path, message: `${prefix}[${name}] ${flow}, but (${place}) is not wired ${linkText} ${by}`}]);
      }
      throw new NetValidationError([{code: "composition.refinement.unfit", path, message: `${prefix}[${name}] ${flow}, but the ${direction} ports of ${by} wired to it carry ${[...portTypes].sort().join(", ")}`}]);
    }
  }
}

/**
 * Each fused place's name and its member qualified names.
 *
 * The fused name is the sorted `__`-concatenation of the class's output
 * port qualified names. Input ports are members but never appear in the
 * name. A class with no output port is named after all of its members.
 * Deterministic regardless of wire ordering.
 */
function fusionClasses(
  qnameToPlace: ReadonlyMap<string, Place>,
  wires: readonly CompositionWire[],
  shares: readonly CompositionShare[],
): {fusedName: string; members: readonly string[]}[] {
  const wireEndpoints = wires.map(
    (wire) =>
      [`${wire.from.net}.${wire.from.port}`, `${wire.to.net}.${wire.to.port}`] as const,
  );
  const shareMembers = shares.map((share) =>
    share.places.map((member) => `${member.net}.${member.place}`),
  );
  const wired = new Set<string>();
  for (const [source, sink] of wireEndpoints) {
    wired.add(source);
    wired.add(sink);
  }
  for (const members of shareMembers) {
    for (const member of members) wired.add(member);
  }
  const unionFind = new UnionFind(wired);
  for (const [source, sink] of wireEndpoints) unionFind.union(source, sink);
  for (const [first, ...rest] of shareMembers) {
    for (const member of rest) unionFind.union(first as string, member);
  }
  const classes = new Map<string, string[]>();
  for (const name of [...wired].sort()) {
    const root = unionFind.find(name);
    const members = classes.get(root) ?? [];
    members.push(name);
    classes.set(root, members);
  }
  const named: {fusedName: string; members: readonly string[]}[] = [];
  for (const members of classes.values()) {
    const sourcePorts = members
      .filter((member) => {
        const port = (qnameToPlace.get(member) as Place).port;
        return port !== undefined && port.direction === "output";
      })
      .sort();
    named.push({
      fusedName: (sourcePorts.length > 0 ? sourcePorts : members).join("__"),
      members,
    });
  }
  return named;
}

/**
 * Every wired or shared place's qualified name (`alias.place`) to the fused
 * place `mergeNets` makes for it.
 */
export function portFusionMap(
  aliasToNet: ReadonlyMap<string, Net>,
  wires: readonly CompositionWire[],
  shares: readonly CompositionShare[] = [],
): ReadonlyMap<string, string> {
  const qnameToPlace = new Map<string, Place>();
  for (const [alias, net] of aliasToNet) {
    for (const place of net.places) qnameToPlace.set(`${alias}.${place.name}`, place);
  }
  const fused = new Map<string, string>();
  for (const {fusedName, members} of fusionClasses(qnameToPlace, wires, shares)) {
    for (const member of members) fused.set(member, fusedName);
  }
  return fused;
}

/**
 * Merge nets under aliases, fusing wired ports into shared places.
 *
 * Returns one {@link Net}. The language implementation re-validates it,
 * including every inline CEL expression, before returning. The package copy
 * returns the merged net without that check. Mirrors the Python `merge_nets`
 * semantics.
 *
 * Each refinement removes its transition and every arc of that transition; the
 * refining net, wired to the same places, takes its part.
 */
export function mergeNets(
  aliasToNet: ReadonlyMap<string, Net>,
  wires: readonly CompositionWire[],
  refinements: readonly CompositionRefinement[] = [],
  shares: readonly CompositionShare[] = [],
  name = "composition",
  final?: readonly (readonly CompositionPlaceEndpoint[])[],
): Net {
  // ── 0. Check refinements; collect the refined transitions' qualified names.
  validateRefinements(refinements, wires, aliasToNet, shares);
  const refined = new Set(refinements.map((r) => `${r.net}.${r.transition}`));

  // ── 1. Qualify places and transitions; index port places by qualified name.
  // A transition without an `actor` annotation takes its net's default actor
  // (the net's own `actor` annotation), so actors survive the merge.
  const qualifiedPlaces: Place[] = [];
  const qnameToPlace = new Map<string, Place>();
  const qualifiedTransitions: Transition[] = [];
  for (const [alias, net] of aliasToNet) {
    const defaultActor = net.annotations?.actor;
    for (const place of net.places) {
      const qname = `${alias}.${place.name}`;
      // description/annotations carry through qualification — doc-only
      // (ADR 0011), but consumers (e.g. the viz fusion-place styling) read them
      // off the merged net. Fused places (step 3) get their own annotations.
      const qualified: Place = {
        name: qname,
        accepts: [...place.accepts],
        ...(place.port === undefined ? {} : {port: place.port}),
        ...(place.description === undefined ? {} : {description: place.description}),
        ...(place.annotations === undefined ? {} : {annotations: place.annotations}),
      };
      qualifiedPlaces.push(qualified);
      qnameToPlace.set(qname, qualified);
    }
    for (const transition of net.transitions) {
      if (refined.has(`${alias}.${transition.name}`)) continue;
      const annotations = withActor(transition.annotations, defaultActor);
      qualifiedTransitions.push({
        name: `${alias}.${transition.name}`,
        ...(transition.handler === undefined ? {} : {handler: transition.handler}),
        ...(transition.guard === undefined ? {} : {guard: transition.guard}),
        ...(transition.priority === undefined ? {} : {priority: transition.priority}),
        // Timer place references qualify like arc endpoints; the fusion rewrite
        // is applied in step 4, once the rewrite map exists. The CEL string is
        // never touched (ADR 0018).
        ...(transition.timer === undefined
          ? {}
          : {timer: mapTimerPlaces(transition.timer, (name) => `${alias}.${name}`)}),
        ...(transition.description === undefined
          ? {}
          : {description: transition.description}),
        ...(annotations === undefined ? {} : {annotations}),
      });
    }
  }

  // ── 2. Build port-fusion equivalence classes via union-find. A wire joins an
  // output port (from) to an input port (to); a share joins places with no
  // direction (ADR 0040). Only wired ports and shared places participate, so
  // an unwired port stays a boundary (no class, no fusion).
  // rewriteMap: every member of a fused class → the fused place name.
  const rewriteMap = new Map<string, string>();
  const fusedPlaces: Place[] = [];
  for (const {fusedName, members} of fusionClasses(qnameToPlace, wires, shares)) {
    const accepts: string[] = [];
    const seen = new Set<string>();
    for (const member of members) {
      for (const type of (qnameToPlace.get(member) as Place).accepts) {
        if (seen.has(type)) continue;
        seen.add(type);
        accepts.push(type);
      }
    }
    const ordered = memberPrecedence(members, qnameToPlace);
    const description = fusedDescription(ordered, qnameToPlace);
    fusedPlaces.push({
      name: fusedName,
      accepts,
      ...(description === undefined ? {} : {description}),
      annotations: fusedAnnotations(ordered, qnameToPlace),
    });
    for (const member of members) rewriteMap.set(member, fusedName);
  }

  // ── 3. Assemble places: unwired/non-port qualified places + fused places.
  const places: Place[] = qualifiedPlaces.filter(
    (place) => !rewriteMap.has(place.name),
  );
  places.push(...fusedPlaces);

  // ── 4. Rewrite arc endpoints and produce destinations to qualified/fused.
  const rewrite = (name: string): string => rewriteMap.get(name) ?? name;

  // Timer place references follow the same fusion rewrite as arc endpoints (a
  // wired clock port fuses into the shared place the timer must read).
  const timedTransitions: Transition[] = qualifiedTransitions.map((transition) =>
    transition.timer === undefined
      ? transition
      : {
          ...transition,
          timer: mapTimerPlaces(transition.timer, (name) => rewrite(name)),
        },
  );

  // Binding names (ADR 0032): each transition's CEL keeps reading `binding`
  // under its constituent's names. A constituent that already declares them
  // (itself a merge) keeps its keys; otherwise the keys are its local place
  // names. Either way only the place values are rewritten.
  const bindingNames = new Map<string, Record<string, string>>();
  for (const [alias, net] of aliasToNet) {
    for (const transition of net.transitions) {
      if (refined.has(`${alias}.${transition.name}`)) continue;
      const local = new Map(Object.entries(transition.bindingNames ?? {}));
      if (transition.bindingNames === undefined) {
        for (const arc of net.arcs) {
          if (
            arc.consume !== undefined &&
            arc.consume.mode !== "inhibit" &&
            arc.to.transition === transition.name &&
            !local.has(arc.from.place)
          ) {
            local.set(arc.from.place, arc.from.place);
          }
        }
      }
      if (local.size === 0) continue;
      bindingNames.set(
        `${alias}.${transition.name}`,
        Object.fromEntries(
          [...local].map(([key, place]) => [key, rewrite(`${alias}.${place}`)]),
        ),
      );
    }
  }
  const transitions: Transition[] = timedTransitions.map((transition) => {
    const names = bindingNames.get(transition.name);
    return names === undefined ? transition : {...transition, bindingNames: names};
  });

  const arcs: Arc[] = [];
  for (const [alias, net] of aliasToNet) {
    for (const arc of net.arcs) {
      const arcTransition = arc.consume !== undefined ? arc.to.transition : arc.from.transition;
      if (refined.has(`${alias}.${arcTransition}`)) continue;
      if (arc.consume !== undefined) {
        arcs.push({
          from: {place: rewrite(`${alias}.${arc.from.place}`)},
          to: {transition: `${alias}.${arc.to.transition}`},
          consume: arc.consume,
          ...(arc.description === undefined ? {} : {description: arc.description}),
          ...(arc.annotations === undefined ? {} : {annotations: arc.annotations}),
        });
      } else {
        const produce = arc.produce;
        arcs.push({
          from: {transition: `${alias}.${arc.from.transition}`},
          to: {place: rewrite(`${alias}.${arc.to.place}`)},
          produce: {
            type: produce.type,
            destination: rewrite(`${alias}.${produce.destination}`),
            ...(produce.data === undefined ? {} : {data: produce.data}),
            ...(produce.cel === undefined ? {} : {cel: produce.cel}),
          },
          ...(arc.description === undefined ? {} : {description: arc.description}),
          ...(arc.annotations === undefined ? {} : {annotations: arc.annotations}),
        });
      }
    }
  }

  // ── 5. Compose initial markings: qualify keys, merge fused-place keys.
  const composed: Record<string, Token[]> = {};
  let hasMarking = false;
  for (const [alias, net] of aliasToNet) {
    if (net.initialMarking === undefined) continue;
    hasMarking = true;
    for (const [key, tokens] of Object.entries(net.initialMarking)) {
      const qualifiedKey = `${alias}.${key}`;
      const target = rewriteMap.get(qualifiedKey) ?? qualifiedKey;
      (composed[target] ??= []).push(...tokens);
    }
  }

  // ── 6. Domains and proof facts (ADR 0037); declared actors (ADR 0038).
  const domains = mergedDomains(aliasToNet);
  const proofs = mergedProofs(aliasToNet, rewrite, arcs, final);
  const actors = mergedActors(aliasToNet);

  const result = {
    name,
    places,
    transitions,
    arcs,
    ...(hasMarking ? {initialMarking: composed} : {}),
    ...(Object.keys(domains).length === 0 ? {} : {domains}),
    ...(proofs === undefined ? {} : {proofs}),
    ...(actors.length === 0 ? {} : {annotations: {actors}}),
  };

  return result as Net;
}

/**
 * Merge a composition document into a single {@link Net}, given its referenced
 * nets already resolved and keyed by their (default- or explicitly-)resolved
 * alias. Delegates to {@link mergeNets} using the document's wires. Unlike the
 * Python `merge_composition`, this never reads files: browser-side resolution
 * (see `resolve-composition.ts`) supplies `aliasToNet`.
 */
export function mergeComposition(
  composition: CompositionDocument,
  aliasToNet: ReadonlyMap<string, Net>,
): Net {
  return mergeNets(
    aliasToNet,
    composition.wires,
    composition.refinements,
    composition.shares,
    composition.name ?? "composition",
    composition.final,
  );
}
