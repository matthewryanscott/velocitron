import {readFileSync} from "node:fs";
import {dirname, isAbsolute, join, resolve} from "node:path";

import {PetrinetDslError, PetrinetResourceError} from "@velocitron/dsl";
import {mergeComposition, NetValidationError as MergeNetValidationError, portFusionMap} from "@velocitron/merge";
import {
  NetValidationError,
  compilePetrinetText,
  parseComposition,
  parseNet,
} from "@velocitron/petrinet";
import type {Play} from "@velocitron/play";
import type {ReadonlyJsonObject} from "@velocitron/engine";

import {PlayCheckError} from "./errors.js";
import type {PlayNet} from "./model.js";

export interface LoadPlayNetOptions {
  /** Directory that relative `net` and `use` paths resolve against. */
  readonly origin?: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function originOf(play: Play, options: LoadPlayNetOptions): string {
  if (options.origin !== undefined) return options.origin;
  if (play.source.includes("/") || play.source.includes("\\")) return dirname(play.source);
  return process.cwd();
}

function fail(
  play: Play,
  message: string,
  line: number,
  column: number,
  details: readonly string[] = [],
): PlayCheckError {
  return new PlayCheckError("SC201", message, line, column, details);
}

function loadDocument(path: string): ReadonlyJsonObject {
  const text = readFileSync(path, "utf8");
  const suffix = path.toLowerCase();
  if (suffix.endsWith(".petrinet")) {
    const compiled = compilePetrinetText(text, path);
    if (!isRecord(compiled.document)) {
      throw new Error(`${path}: a net document is a JSON object`);
    }
    return compiled.document;
  }
  if (suffix.endsWith(".json")) {
    const document: unknown = JSON.parse(text);
    if (!isRecord(document)) throw new Error(`${path}: a net document is a JSON object`);
    return document as ReadonlyJsonObject;
  }
  throw new Error(`unsupported net file type ${path}`);
}

function placeNamesOf(net: PlayNet["net"]): Map<string, string> {
  return new Map(net.places.map((place) => [place.name, place.name]));
}

/**
 * Resolve the play's `net` line, or its `use` / `wire` / `share` / `refine`
 * lines, to one engine net (SC201 / SC212).
 *
 * TypeScript compilation has no `validateIr` switch. An invalid contribution
 * fails at the compiler or at `parseNet`, and that failure is still SC201.
 */
export function loadPlayNet(play: Play, options: LoadPlayNetOptions = {}): PlayNet {
  const origin = originOf(play, options);
  const position = play.position;
  const both = play.net !== null && (
    play.uses.length > 0 || play.wires.length > 0 || play.refines.length > 0 || play.shares.length > 0
  );
  if (both) {
    const where = play.uses[0]?.position ?? position;
    throw new PlayCheckError(
      "SC212",
      "a play names one `net` or composes with `use`, `wire`, `share` and `refine`, not both",
      where.line,
      where.column,
    );
  }
  if (play.net === null && play.uses.length === 0) {
    throw new PlayCheckError(
      "SC212",
      'a play needs `net "file"` or `use "file" as alias` lines',
      position.line,
      position.column,
    );
  }

  try {
    if (play.net !== null) {
      const path = isAbsolute(play.net) ? play.net : resolve(origin, play.net);
      const document = loadDocument(path);
      if (!("nets" in document)) {
        const net = parseNet(document);
        return {
          net,
          label: play.net,
          document,
          placeNames: placeNamesOf(net),
          composed: false,
          refined: new Map(),
        };
      }
      return loadComposition(play, document, dirname(path), play.net);
    }
    const document = {
      nets: play.uses.map((use) => ({ref: use.ref, alias: use.alias})),
      wires: play.wires.map((wire) => ({
        from: {net: wire.fromAlias, port: wire.fromPlace},
        to: {net: wire.toAlias, port: wire.toPlace},
      })),
      refinements: play.refines.map((refine) => ({
        net: refine.alias,
        transition: refine.transition,
        by: refine.by,
      })),
      shares: play.shares.map((share) => ({
        places: share.members.map(([alias, place]) => ({net: alias, place})),
      })),
    };
    const where = play.uses[0]?.position ?? position;
    const label = play.uses.map((use) => `${use.alias} = ${use.ref}`).join(", ");
    return loadComposition(play, document, origin, label, where.line, where.column);
  } catch (error) {
    if (error instanceof PlayCheckError) throw error;
    const where = play.uses[0]?.position ?? position;
    if (error instanceof PetrinetDslError || error instanceof PetrinetResourceError) {
      throw fail(play, "the net does not compile", where.line, where.column, [error.message]);
    }
    if (
      error instanceof NetValidationError
      || error instanceof MergeNetValidationError
      || error instanceof Error
    ) {
      throw fail(play, `the net cannot be loaded: ${error.message}`, where.line, where.column);
    }
    throw error;
  }
}

function loadComposition(
  play: Play,
  document: unknown,
  origin: string,
  label: string,
  line = play.position.line,
  column = play.position.column,
): PlayNet {
  const parsed = parseComposition(document, {
    origin,
    loadRef: (ref) => {
      const path = isAbsolute(ref) ? ref : join(origin, ref);
      return loadDocument(path);
    },
  });
  let net;
  try {
    net = mergeComposition(parsed.document, parsed.parsedNets);
  } catch (error) {
    if (error instanceof MergeNetValidationError) {
      throw fail(play, `the net cannot be loaded: ${error.message}`, line, column);
    }
    throw error;
  }
  const fusion = portFusionMap(parsed.parsedNets, parsed.document.wires, parsed.document.shares ?? []);
  const placeNames = placeNamesOf(net);
  for (const [qualified, fused] of fusion) placeNames.set(qualified, fused);
  const refined = new Map<string, string>();
  for (const refinement of parsed.document.refinements ?? []) {
    refined.set(`${refinement.net}.${refinement.transition}`, refinement.by);
  }
  return {
    net,
    label,
    document: null,
    placeNames,
    composed: true,
    refined,
  };
}
