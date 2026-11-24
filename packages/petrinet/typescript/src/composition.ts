import {
  findPort,
  mergeComposition as mergeMergeComposition,
  mergeNets as mergeMergeNets,
  validateRefinements as mergeValidateRefinements,
  NetValidationError as MergeNetValidationError,
} from "@velocitron/merge";
import {pythonStringRepr} from "@velocitron/dsl";
import {deepFreezeJson} from "./json.js";
import {parseNet} from "./parse.js";
import type {
  CompositionDocument,
  CompositionPlaceEndpoint,
  CompositionRefinement,
  CompositionShare,
  CompositionWire,
  Net,
  Port,
} from "./types.js";
import {validateCompositionDocumentShape} from "./validate.js";
import {NetValidationError, type NetValidationIssue} from "./errors.js";

/** Validates only the canonical composition document shape; it never loads or merges refs. */
export function parseCompositionShape(input: unknown): CompositionDocument {
  const document = validateCompositionDocumentShape(input) as unknown as CompositionDocument;
  return deepFreezeJson(document);
}

/**
 * The composition loading seam — the TypeScript twin of Python's
 * `parse_composition` (`velocitron_petrinet.parse`): refs resolution, alias
 * defaults, and shape validation. This returns the parsed nets a caller
 * hands to `mergeComposition`.
 */
export type CompositionLoader = (ref: string) => unknown;

export interface ParseCompositionOptions {
  /**
   * Resolution base, mirroring Python's `origin`. Relative references in an
   * in-memory document require an explicit `origin` unless the injected net
   * loader resolves the literal reference itself. This seam supplies the
   * value for loader context only: the loader owns resolution.
   */
  readonly origin?: string;
  /**
   * The injected net loader. There is deliberately NO filesystem default
   * (browser-safe posture: no fs/path/process). The loader MUST return
   * canonical net JSON source material — never an already-parsed `Net` —
   * and every result stays source material that passes through
   * {@link parseNet}. Omitting it and referencing any net raises
   * `composition.loader_missing` (browser-safe: no filesystem fallback).
   */
  readonly loadRef?: CompositionLoader;
}

/**
 * The validated composition, flattened (ADR 0041): a referenced composition's
 * nets appear under `<alias>.<inner alias>` in `parsedNets`, and the document's
 * `nets`, `wires`, `shares` and `refinements` name them that way. Each `nets`
 * entry's `ref` is the reference rebased onto this composition, as in
 * `sources` (flattened alias -> rebased reference).
 */
export interface ParsedComposition {
  readonly document: CompositionDocument;
  readonly parsedNets: ReadonlyMap<string, Net>;
  readonly sources: ReadonlyMap<string, string>;
}

const ALIAS_PATTERN = /^[A-Za-z_][A-Za-z0-9_]*$/;

function fail(issues: readonly NetValidationIssue[]): never {
  throw new NetValidationError(issues);
}

function resolveWirePort(
  endpoint: {readonly net: string; readonly port: string},
  role: "source" | "target",
  direction: Port["direction"],
  aliasToNet: ReadonlyMap<string, Net>,
  pointer: string,
): Port {
  const {net: alias, port: portName} = endpoint;
  const net = aliasToNet.get(alias);
  if (net === undefined) {
    fail([
      {code: "composition.alias_unknown", path: `${pointer}/net`, message: `wire references unknown net alias: ${JSON.stringify(alias)}`},
    ]);
  }
  const port = findPort(net, portName);
  if (port === undefined) {
    fail([
      {code: "composition.port_undeclared", path: `${pointer}/port`, message: `net ${JSON.stringify(alias)} has no port named ${JSON.stringify(portName)}`},
    ]);
  }
  if (port.direction !== direction) {
    fail([
      {code: "composition.port_direction", path: `${pointer}/port`, message: `wire ${role} ${JSON.stringify(`${alias}.${portName}`)} declares direction ${JSON.stringify(port.direction)}, expected ${JSON.stringify(direction)}`},
    ]);
  }
  return port;
}

function validateWires(
  wires: readonly CompositionWire[],
  aliasToNet: ReadonlyMap<string, Net>,
): void {
  for (const [index, wire] of wires.entries()) {
    const fromPort = resolveWirePort(
      wire.from,
      "source",
      "output",
      aliasToNet,
      `/wires/${index}/from`,
    );
    const toPort = resolveWirePort(
      wire.to,
      "target",
      "input",
      aliasToNet,
      `/wires/${index}/to`,
    );
    if (fromPort.type !== toPort.type) {
      fail([
        {code: "composition.wire.type_mismatch", path: `/wires/${index}`, message: `wired ports carry different types: ${JSON.stringify(fromPort.type)} -> ${JSON.stringify(toPort.type)}`},
      ]);
    }
  }
}

/**
 * Merge nets, then revalidate the result with {@link parseNet}.
 *
 * `@velocitron/merge`'s `mergeNets` does not compile CEL or recheck the
 * merged document. This close does.
 */
export function mergeNets(
  aliasToNet: ReadonlyMap<string, Net>,
  wires: readonly CompositionWire[],
  refinements: readonly CompositionRefinement[] = [],
  shares: readonly CompositionShare[] = [],
  name = "composition",
  final?: readonly (readonly CompositionPlaceEndpoint[])[],
): Net {
  try {
    return parseNet(mergeMergeNets(
      aliasToNet,
      wires,
      refinements,
      shares,
      name,
      final,
    ));
  } catch (error) {
    if (error instanceof MergeNetValidationError) {
      throw new NetValidationError(error.issues as readonly NetValidationIssue[]);
    }
    throw error;
  }
}

/** Merge a composition whose nets are already parsed, then revalidate. */
export function mergeComposition(
  composition: CompositionDocument,
  aliasToNet: ReadonlyMap<string, Net>,
): Net {
  try {
    return parseNet(mergeMergeComposition(composition, aliasToNet));
  } catch (error) {
    if (error instanceof MergeNetValidationError) {
      throw new NetValidationError(error.issues as readonly NetValidationIssue[]);
    }
    throw error;
  }
}

export function validateRefinements(
  refinements: readonly CompositionRefinement[],
  wires: readonly CompositionWire[],
  aliasToNet: ReadonlyMap<string, Net>,
  shares: readonly CompositionShare[] = [],
): void {
  try {
    mergeValidateRefinements(refinements, wires, aliasToNet, shares);
  } catch (error) {
    if (error instanceof MergeNetValidationError) {
      throw new NetValidationError(error.issues as readonly NetValidationIssue[]);
    }
    throw error;
  }
}

/**
 * Parses and validates a composition and each referenced net.
 *
 * Validates the document against the canonical composition schema, then for
 * each `nets[]` entry resolves `ref` through the injected loader (a loader
 * failure becomes `composition.loader_failed`), parses the returned source
 * material through {@link parseNet} (an invalid constituent net becomes
 * `composition.ref_invalid`), defaults a missing `alias` to the referenced
 * net's `name` — enforcing the simple-identifier invariant the schema's
 * `pattern` cannot reach for derived defaults (spec/composition.md, D4) —
 * enforces alias uniqueness, and resolves every wire endpoint (unknown
 * alias, missing port name, direction, and type compatibility) and every
 * share before anything can merge. A reference may name another composition
 * document; it is parsed the same way and flattened into this one.
 *
 * Returns the validated document with alias defaults applied plus the parsed
 * nets keyed by alias, closing the validate→merge TOCTOU window at no extra
 * parsing cost (mirroring Python's `parsed_nets`).
 *
 * References: spec/composition.md; ADR 0004, ADR 0040, ADR 0041.
 */
export function parseComposition(
  document: unknown,
  options: ParseCompositionOptions,
): ParsedComposition {
  const shape = parseCompositionShape(document);
  const flat = parseCompositionDocument(shape, options.loadRef, "", []);
  return {
    document: deepFreezeJson<CompositionDocument>({
      ...(shape.name === undefined ? {} : {name: shape.name}),
      nets: [...flat.sources].map(([alias, ref]) => ({ref, alias})),
      wires: flat.wires,
      ...(flat.shares.length === 0 ? {} : {shares: flat.shares}),
      ...(flat.refinements.length === 0 && !flat.writtenRefinements ? {} : {refinements: flat.refinements}),
      ...(flat.final === undefined ? {} : {final: flat.final}),
    }),
    parsedNets: flat.aliasToNet,
    sources: flat.sources,
  };
}

interface FlatComposition {
  readonly aliasToNet: Map<string, Net>;
  readonly sources: Map<string, string>;
  readonly wires: readonly CompositionWire[];
  readonly shares: readonly CompositionShare[];
  readonly refinements: readonly CompositionRefinement[];
  /** Whether the document itself declares `refinements`, even an empty list. */
  readonly writtenRefinements: boolean;
  /** The document's own final markings; a referenced composition's do not carry over. */
  readonly final?: readonly (readonly CompositionPlaceEndpoint[])[];
}

function isAbsolutePath(path: string): boolean {
  return path.startsWith("/");
}

/** POSIX `normpath`, as Python's `posixpath.normpath` computes it. */
function normalizePath(path: string): string {
  if (path === "") return ".";
  const leading = path.startsWith("//") && !path.startsWith("///") ? "//" : path.startsWith("/") ? "/" : "";
  const parts: string[] = [];
  for (const part of path.split("/")) {
    if (part === "" || part === ".") continue;
    if (part !== ".." || (leading === "" && parts.length === 0) || parts.at(-1) === "..") {
      parts.push(part);
    } else if (parts.length > 0) {
      parts.pop();
    }
  }
  const joined = leading + parts.join("/");
  return joined === "" ? "." : joined;
}

/** POSIX `dirname`, as Python's `posixpath.dirname` computes it. */
function directoryOf(path: string): string {
  const head = path.slice(0, path.lastIndexOf("/") + 1);
  return head !== "" && head !== "/".repeat(head.length) ? head.replace(/\/+$/u, "") : head;
}

/** `ref`, written in a composition in directory `base`, as the outermost composition sees it. */
function rebase(base: string, ref: string): string {
  if (base === "" || isAbsolutePath(ref)) return ref;
  return normalizePath(base.endsWith("/") ? `${base}${ref}` : `${base}/${ref}`);
}

/**
 * Split `path` inside the composition `alias` into the flattened alias of the
 * net that holds it and the name in that net: `gate.sending` inside
 * `lifecycle` is `["lifecycle.gate", "sending"]`. The longest matching inner
 * alias wins, so a place name may hold a dot.
 */
function innerPath(
  alias: string,
  path: string,
  leaves: Iterable<string>,
): [string, string] | undefined {
  let best: string | undefined;
  for (const leaf of leaves) {
    if (!leaf.startsWith(`${alias}.`)) continue;
    if (path.startsWith(`${leaf.slice(alias.length + 1)}.`) && (best === undefined || leaf.length > best.length)) {
      best = leaf;
    }
  }
  if (best === undefined) return undefined;
  return [best, path.slice(best.length - alias.length)];
}

function isCompositionSource(loaded: unknown): boolean {
  return typeof loaded === "object" && loaded !== null && !Array.isArray(loaded) && Object.hasOwn(loaded, "nets");
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

const MISSING_LEAF_CODES = {
  port: "composition.port_undeclared",
  place: "composition.share.place_unknown",
  transition: "composition.refinement.transition_unknown",
} as const;

/**
 * Parse one composition document, flattening every composition it uses
 * (ADR 0041): a nested composition's nets become `<alias>.<inner alias>`, and
 * its relative references are rebased onto this composition's directory
 * before the loader sees them. Messages match the Python
 * `_parse_composition_document`.
 */
function parseCompositionDocument(
  shapeOnly: CompositionDocument,
  loadRef: CompositionLoader | undefined,
  base: string,
  stack: readonly string[],
): FlatComposition {
  const aliasToNet = new Map<string, Net>();
  const sources = new Map<string, string>();
  const composed = new Map<string, FlatComposition>();
  for (const [index, entry] of shapeOnly.nets.entries()) {
    const ref = entry.ref;
    const path = `/nets/${index}/ref`;
    if (loadRef === undefined) {
      fail([
        {code: "composition.loader_missing", path, message: `relative composition net reference ${JSON.stringify(ref)} requires origin unless a net loader resolves the literal reference itself`},
      ]);
    }
    const rebased = rebase(base, ref);
    const key = normalizePath(rebased);
    if (stack.includes(key)) {
      fail([
        {code: "composition.reference_cycle", path, message: `composition reference cycle: ${[...stack, key].join(" -> ")}`},
      ]);
    }
    let loaded: unknown;
    try {
      loaded = loadRef(rebased);
    } catch (error: unknown) {
      fail([
        {code: "composition.loader_failed", path, message: `composition loader failed for reference ${JSON.stringify(rebased)}: ${errorMessage(error)}`},
      ]);
    }
    let alias = entry.alias;
    let inner: FlatComposition | undefined;
    let parsed: Net | undefined;
    try {
      if (isCompositionSource(loaded)) {
        if (alias === undefined) {
          fail([
            {code: "composition.ref_invalid", path, message: "a composition used inside another needs an explicit alias"},
          ]);
        }
        inner = parseCompositionDocument(parseCompositionShape(loaded), loadRef, directoryOf(rebased), [...stack, key]);
      } else {
        parsed = parseNet(loaded);
      }
    } catch (error: unknown) {
      fail([
        {code: "composition.ref_invalid", path, message: `invalid referenced net ${JSON.stringify(ref)}: ${errorMessage(error)}`},
      ]);
    }
    if (alias === undefined) {
      const net = parsed as Net;
      // Default to the referenced net's `name` when no explicit alias is
      // given. A derived alias bypasses the schema's `pattern`, so enforce
      // the identifier invariant here: a non-identifier net name (e.g.
      // "prod.line") would make `<alias>.<placeName>` ambiguous.
      // References: spec/composition.md (default aliasing; aliasing rationale).
      alias = net.name;
      if (!ALIAS_PATTERN.test(alias)) {
        fail([
          {code: "composition.alias_derived_invalid", path, message: `derived composition alias ${JSON.stringify(alias)} (from net name) is not a simple identifier; supply an explicit \`alias\` (pattern ${ALIAS_PATTERN.source})`},
        ]);
      }
    }
    if (aliasToNet.has(alias) || composed.has(alias)) {
      fail([
        {code: "composition.duplicate_alias", path: `/nets/${index}/alias`, message: `duplicate composition alias: ${JSON.stringify(alias)}`},
      ]);
    }
    if (inner !== undefined) {
      composed.set(alias, inner);
      for (const [innerAlias, innerNet] of inner.aliasToNet) {
        aliasToNet.set(`${alias}.${innerAlias}`, innerNet);
        sources.set(`${alias}.${innerAlias}`, inner.sources.get(innerAlias) as string);
      }
    } else {
      aliasToNet.set(alias, parsed as Net);
      sources.set(alias, rebased);
    }
  }

  /** A written alias and name, as the flattened net alias and name. */
  const resolve = (
    alias: string,
    name: string,
    kind: keyof typeof MISSING_LEAF_CODES,
    path: string,
    label = "",
  ): [string, string] => {
    if (!composed.has(alias)) return [alias, name];
    const leaf = innerPath(alias, name, aliasToNet.keys());
    if (leaf === undefined) {
      fail([
        {code: MISSING_LEAF_CODES[kind], path, message: `${label}net ${pythonStringRepr(alias)} has no ${kind} named ${pythonStringRepr(name)}`},
      ]);
    }
    return leaf;
  };

  // The nested compositions' own wires, shares and refinements, under their
  // flattened aliases. They were validated when they were parsed.
  const wires: CompositionWire[] = [];
  const shares: CompositionShare[] = [];
  const refinements: CompositionRefinement[] = [];
  for (const [alias, inner] of composed) {
    for (const wire of inner.wires) {
      wires.push({
        from: {net: `${alias}.${wire.from.net}`, port: wire.from.port},
        to: {net: `${alias}.${wire.to.net}`, port: wire.to.port},
      });
    }
    for (const share of inner.shares) {
      shares.push({places: share.places.map((member) => ({net: `${alias}.${member.net}`, place: member.place}))});
    }
    for (const refinement of inner.refinements) {
      refinements.push({
        net: `${alias}.${refinement.net}`,
        transition: refinement.transition,
        by: `${alias}.${refinement.by}`,
      });
    }
  }

  const ownWires = shapeOnly.wires.map((wire, index): CompositionWire => {
    const [fromNet, fromPort] = resolve(wire.from.net, wire.from.port, "port", `/wires/${index}/from/port`);
    const [toNet, toPort] = resolve(wire.to.net, wire.to.port, "port", `/wires/${index}/to/port`);
    return {from: {net: fromNet, port: fromPort}, to: {net: toNet, port: toPort}};
  });
  validateWires(ownWires, aliasToNet);
  wires.push(...ownWires);

  for (const [index, share] of (shapeOnly.shares ?? []).entries()) {
    const path = `/shares/${index}`;
    const label = `share ${share.places.map((member) => `${member.net}.(${member.place})`).join(" ~ ")}`;
    for (const member of share.places) {
      if (!aliasToNet.has(member.net) && !composed.has(member.net)) {
        fail([{code: "composition.share.alias_unknown", path, message: `${label}: unknown alias ${member.net}`}]);
      }
    }
    const members = share.places.map((member) => resolve(member.net, member.place, "place", path, `${label}: `));
    validateShare(label, members, aliasToNet, path);
    shares.push({places: members.map(([net, place]) => ({net, place}))});
  }

  for (const [index, refinement] of (shapeOnly.refinements ?? []).entries()) {
    const path = `/refinements/${index}`;
    const label = `refine ${refinement.net}.[${refinement.transition}] by ${refinement.by}: `;
    if (composed.has(refinement.by)) {
      fail([
        {code: "composition.refinement.by_composition", path, message: `${label}${refinement.by} is a composition; a refining net must be a net`},
      ]);
    }
    const [net, transition] = resolve(refinement.net, refinement.transition, "transition", path, label);
    refinements.push({net, transition, by: refinement.by});
  }
  validateRefinements(refinements, wires, aliasToNet, shares);

  const final = shapeOnly.final?.map((marking, index) => {
    const path = `/final/${index}`;
    const label = `final ${marking.map((member) => `${member.net}.(${member.place})`).join(" + ")}`;
    for (const member of marking) {
      if (!aliasToNet.has(member.net) && !composed.has(member.net)) {
        fail([{code: "composition.final.alias_unknown", path, message: `${label}: unknown alias ${member.net}`}]);
      }
    }
    const members = marking.map((member) => resolve(member.net, member.place, "place", path, `${label}: `));
    for (const [netAlias, placeName] of members) {
      if (!(aliasToNet.get(netAlias) as Net).places.some((place) => place.name === placeName)) {
        fail([
          {code: "composition.final.place_unknown", path, message: `${label}: net ${pythonStringRepr(netAlias)} has no place named ${pythonStringRepr(placeName)}`},
        ]);
      }
    }
    if (new Set(members.map((member) => JSON.stringify(member))).size !== members.length) {
      fail([{code: "composition.final.duplicate_member", path, message: `${label}: names a place more than once`}]);
    }
    return members.map(([net, place]) => ({net, place}));
  });

  return {
    aliasToNet,
    sources,
    wires,
    shares,
    refinements,
    writtenRefinements: shapeOnly.refinements !== undefined,
    ...(final === undefined ? {} : {final}),
  };
}

/** Each member names a place, no place twice, and all accept the same colors. */
function validateShare(
  label: string,
  members: readonly (readonly [string, string])[],
  aliasToNet: ReadonlyMap<string, Net>,
  path: string,
): void {
  if (new Set(members.map((member) => JSON.stringify(member))).size !== members.length) {
    fail([{code: "composition.share.duplicate_member", path, message: `${label}: a place is shared with itself`}]);
  }
  let first: {net: string; place: string; accepts: string[]} | undefined;
  for (const [netAlias, placeName] of members) {
    const place = (aliasToNet.get(netAlias) as Net).places.find((candidate) => candidate.name === placeName);
    if (place === undefined) {
      fail([
        {code: "composition.share.place_unknown", path, message: `${label}: net ${pythonStringRepr(netAlias)} has no place named ${pythonStringRepr(placeName)}`},
      ]);
    }
    const accepts = [...place.accepts].sort();
    if (first === undefined) {
      first = {net: netAlias, place: placeName, accepts};
    } else if (accepts.join("\n") !== first.accepts.join("\n")) {
      fail([
        {code: "composition.share.colors", path, message: `${label}: ${netAlias}.(${placeName}) accepts ${accepts.join(", ")}, but ${first.net}.(${first.place}) accepts ${first.accepts.join(", ")}`},
      ]);
    }
  }
}