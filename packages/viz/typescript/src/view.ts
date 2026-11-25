/**
 * Apply an authored view to a rendered net.
 *
 * Positions and routes come from the reserved payload
 * `annotations["petrinet.dsl/v1"]`. The pass rewrites statement lines
 * through the render model's index. It does not parse the DOT text to
 * discover which line belongs to which place.
 */

import type {BesidePlacement, RenderModel} from "./render.js";

export const DEFAULT_VIEW = "default";
// Shared with the Python renderer (ADR 0067). Helvetica's average advance
// is half the point size. Names are 14pt; color and behavior lines are 9pt.
export const NAME_POINT = 14;
export const SMALL_POINT = 9;
export const NODE_PAD = 20;
export const BESIDE_MARGIN = 24;

export function textWidth(text: string, pointSize: number): number {
  return (text.length * pointSize) / 2;
}

export function nodeWidth(lines: readonly (readonly [string, number])[]): number {
  const widest = lines.reduce((width, [text, size]) => Math.max(width, textWidth(text, size)), 0);
  return widest + NODE_PAD;
}

export function besideGap(transitionWidth: number, copyWidth: number): number {
  return (transitionWidth + copyWidth) / 2 + BESIDE_MARGIN;
}
const VIEW_SPLINES = ["ortho", "spline", "curved", "polyline", "line"] as const;

export class ViewApplicationError extends Error {
  override readonly name = "ViewApplicationError";

  constructor(message: string) {
    super(message);
  }
}

export interface Decoration {
  readonly highlight?: boolean;
  readonly highlightLabel?: string | null;
  readonly note?: string | null;
  readonly summary?: string | null;
  readonly beside?: boolean;
  readonly besideSide?: string | null;
  readonly failure?: boolean;
  readonly faded?: boolean;
}

export interface Decorations {
  readonly nodes: Readonly<Record<string, Decoration>>;
  readonly arcs: Readonly<Record<number, Decoration>>;
  readonly quietColors: readonly string[];
  readonly shownFields: Readonly<Record<string, readonly string[]>>;
}

export function hasView(raw: unknown, viewName: string): boolean {
  const views = viewsOf(raw);
  return views !== undefined && Object.prototype.hasOwnProperty.call(views, viewName);
}

export function viewSetting(raw: unknown, viewName: string, member: string): string | undefined {
  const view = viewOf(raw, viewName);
  if (view === undefined) return undefined;
  const value = view[member];
  return typeof value === "string" ? value : undefined;
}

export function readDecorations(raw: unknown): Decorations {
  const payload = payloadOf(raw);
  if (payload === undefined) {
    return {nodes: {}, arcs: {}, quietColors: [], shownFields: {}};
  }
  const rawDecorations = payload.decorations ?? {};
  if (!isRecord(rawDecorations)) throw new ViewApplicationError("invalid decorations");
  const nodes: Record<string, Decoration> = {};
  const arcs: Record<number, Decoration> = {};
  const quietColors: string[] = [];
  const shownFields: Record<string, readonly string[]> = {};
  for (const [subject, rawEntry] of Object.entries(rawDecorations)) {
    const separator = subject.indexOf(":");
    const kind = separator === -1 ? subject : subject.slice(0, separator);
    const name = separator === -1 ? "" : subject.slice(separator + 1);
    if (!isRecord(rawEntry)) {
      throw new ViewApplicationError(`invalid decoration ${pyStr(subject)}`);
    }
    if (kind === "color") {
      if (rawEntry.quiet === true) quietColors.push(name);
      const shown = rawEntry.show;
      if (shown !== undefined) {
        if (!Array.isArray(shown) || !shown.every((path) => typeof path === "string")) {
          throw new ViewApplicationError(`invalid decoration ${pyStr(subject)}`);
        }
        shownFields[name] = shown;
      }
      continue;
    }
    const highlight = rawEntry.highlight;
    const beside = rawEntry.beside;
    const decoration: Decoration = {
      highlight: isRecord(highlight),
      highlightLabel: isRecord(highlight) ? optionalText(highlight.label) : null,
      note: optionalText(rawEntry.note),
      summary: optionalText(rawEntry.summary),
      beside: isRecord(beside),
      besideSide: isRecord(beside) ? optionalText(beside.side) : null,
    };
    if (kind === "place" || kind === "transition") nodes[subject] = decoration;
    else if (kind === "arc") {
      const handles = payload.arcHandles;
      if (!isRecord(handles) || !isRecord(handles[name])) {
        throw new ViewApplicationError(
          `decoration references unknown arc handle ${pyStr(name)}`,
        );
      }
      const index = handles[name].index;
      if (typeof index !== "number" || !Number.isInteger(index)) {
        throw new ViewApplicationError(
          `decoration references unknown arc handle ${pyStr(name)}`,
        );
      }
      arcs[index] = decoration;
    } else {
      throw new ViewApplicationError(`invalid decoration subject ${pyStr(subject)}`);
    }
  }
  return {nodes, arcs, quietColors, shownFields};
}

export function resolvePositions(
  viewName: string,
  positions: Readonly<Record<string, unknown>>,
): Record<string, readonly [number, number]> {
  const resolved: Record<string, readonly [number, number]> = {};
  const pending = new Map<string, readonly [string, number, number]>();
  for (const [subject, entry] of Object.entries(positions)) {
    if (isRecord(entry) && "from" in entry) {
      const context = `invalid relative position for ${pyStr(subject)} in view ${pyStr(viewName)}`;
      const keys = Object.keys(entry);
      if (
        keys.length !== 2 ||
        !keys.includes("from") ||
        !keys.includes("delta") ||
        typeof entry.from !== "string"
      ) {
        throw new ViewApplicationError(context);
      }
      validateSubject(entry.from, viewName);
      const delta = point(entry.delta, context);
      pending.set(subject, [entry.from, delta[0], delta[1]]);
    } else {
      resolved[subject] = point(entry, `invalid position in view ${pyStr(viewName)}`);
    }
  }
  while (pending.size > 0) {
    let progressed = false;
    for (const [subject, [base, dx, dy]] of [...pending]) {
      const origin = resolved[base];
      if (origin !== undefined) {
        resolved[subject] = [origin[0] + dx, origin[1] + dy];
        pending.delete(subject);
        progressed = true;
      } else if (!Object.prototype.hasOwnProperty.call(positions, base)) {
        throw new ViewApplicationError(
          `view ${pyStr(viewName)} relative position for ${pyStr(subject)} references unpositioned subject ${pyStr(base)}`,
        );
      }
    }
    if (!progressed) {
      const cycle = [...pending.keys()].sort().join(", ");
      throw new ViewApplicationError(
        `view ${pyStr(viewName)} has a relative position cycle among: ${cycle}`,
      );
    }
  }
  return resolved;
}

export function applyView(model: RenderModel, raw: unknown, viewName: string): string {
  const facts = viewFacts(raw, viewName);
  const resolved = resolvePositions(viewName, facts.positions);
  const payload = payloadOf(raw);
  const handles = payload?.arcHandles;
  if (!isRecord(handles)) {
    throw new ViewApplicationError(`view ${pyStr(viewName)} references no arcHandle map`);
  }
  const routeByArc = validateRoutes(viewName, facts.routes, handles);
  const lines = model.dot.split("\n");
  if (lines.at(-1) === "") lines.pop();
  // Copy entry, then the whole place, then beside (ADR 0072).
  const pinned = new Set<number>();
  const copyPoints = new Map<number, readonly [number, number]>();
  for (const [subject, pointValue] of Object.entries(resolved)) {
    const parsed = copyTarget(subject);
    if (parsed === undefined) continue;
    const lineIndex = model.copyLines.get(copyLineKey(parsed[0], parsed[1]));
    if (lineIndex === undefined) {
      throw new ViewApplicationError(
        `view ${pyStr(viewName)} positions unknown subject ${pyStr(subject)}`,
      );
    }
    const previous = copyPoints.get(lineIndex);
    if (previous !== undefined && (previous[0] !== pointValue[0] || previous[1] !== pointValue[1])) {
      throw new ViewApplicationError(
        `view ${pyStr(viewName)} gives the shared copy of place ${pyStr(parsed[0])} two positions`,
      );
    }
    copyPoints.set(lineIndex, pointValue);
  }
  for (const [lineIndex, pointValue] of copyPoints) {
    paint(lines, lineIndex, `${pointValue[0]},${pointValue[1]}!`);
    pinned.add(lineIndex);
  }
  for (const [subject, pointValue] of Object.entries(resolved)) {
    if (copyTarget(subject) !== undefined) continue;
    validateSubject(subject, viewName);
    const lineIndexes = model.nodeLines[subject];
    if (lineIndexes === undefined || lineIndexes.length === 0) {
      throw new ViewApplicationError(
        `view ${pyStr(viewName)} positions unknown subject ${pyStr(subject)}`,
      );
    }
    const rendered = `${pointValue[0]},${pointValue[1]}!`;
    for (const lineIndex of lineIndexes) {
      if (pinned.has(lineIndex)) continue;
      paint(lines, lineIndex, rendered);
      pinned.add(lineIndex);
    }
  }
  for (const [arcIndexText, route] of routeByArc) {
    const arcIndex = Number(arcIndexText);
    if (arcIndex < 0 || arcIndex >= model.arcLines.length) {
      throw new ViewApplicationError(
        `view ${pyStr(viewName)} route ${pyStr(route.handle)} references arc index ${arcIndex} beyond the rendered arcs`,
      );
    }
    const rendered = route.points.map((item) => `${item[0]},${item[1]}`).join(" ");
    const lineIndex = model.arcLines[arcIndex];
    if (lineIndex === undefined) {
      throw new ViewApplicationError(
        `view ${pyStr(viewName)} route ${pyStr(route.handle)} references arc index ${arcIndex} beyond the rendered arcs`,
      );
    }
    const line = lines[lineIndex];
    if (line === undefined) {
      throw new ViewApplicationError(
        `render model statement line does not end a statement: ${pyStr("")}`,
      );
    }
    lines[lineIndex] = posStatementLine(line, rendered);
  }
  const splines = viewSetting(raw, viewName, "splines") ?? "ortho";
  if (!VIEW_SPLINES.includes(splines as (typeof VIEW_SPLINES)[number])) {
    throw new ViewApplicationError(
      `view ${pyStr(viewName)} has invalid splines ${pyStr(splines)}`,
    );
  }
  let graphAttrs = [`    splines=${splines};`];
  if (Object.keys(resolved).length > 0) {
    graphAttrs = [
      "    layout=neato;",
      "    inputscale=72;",
      "    overlap=scale;",
      ...graphAttrs,
    ];
    // Rank clusters are for `dot`. `neato` ignores them, and the invisible
    // edges would stay as springs. Beside places a copy the view did not
    // position.
    pinBeside(lines, model, resolved, pinned);
    for (const lineIndex of [...model.besideLines].sort((left, right) => right - left)) {
      lines.splice(lineIndex, 1);
    }
  }
  lines.splice(model.graphAttrLine, 0, ...graphAttrs);
  return `${lines.join("\n")}\n`;
}

function viewFacts(
  raw: unknown,
  viewName: string,
): {positions: Record<string, unknown>; routes: Record<string, unknown>} {
  const view = viewOf(raw, viewName);
  if (view === undefined) throw new ViewApplicationError(`unknown view ${pyStr(viewName)}`);
  const positions = view.positions;
  const routes = view.routes;
  if (!isRecord(positions) || !isRecord(routes)) {
    throw new ViewApplicationError(`invalid view ${pyStr(viewName)}`);
  }
  return {positions, routes};
}

function validateRoutes(
  viewName: string,
  routes: Readonly<Record<string, unknown>>,
  handles: Readonly<Record<string, unknown>>,
): Map<number, {handle: string; points: Array<readonly [number, number]>}> {
  const routeByArc = new Map<number, {handle: string; points: Array<readonly [number, number]>}>();
  for (const [handle, rawRoute] of Object.entries(routes)) {
    if (!isRecord(rawRoute)) throw new ViewApplicationError(`invalid route in view ${pyStr(viewName)}`);
    const rawPoints = rawRoute.points;
    if (rawRoute.style !== "orthogonal" || !Array.isArray(rawPoints) || rawPoints.length === 0) {
      throw new ViewApplicationError(`invalid route in view ${pyStr(viewName)}`);
    }
    const points = rawPoints.map((item) => point(item, `invalid route in view ${pyStr(viewName)}`));
    const handleValue = handles[handle];
    if (!isRecord(handleValue) || typeof handleValue.index !== "number" || !Number.isInteger(handleValue.index)) {
      throw new ViewApplicationError(
        `view ${pyStr(viewName)} route references unknown arc handle ${pyStr(handle)}`,
      );
    }
    routeByArc.set(handleValue.index, {handle, points});
  }
  return routeByArc;
}

function pinBeside(
  lines: string[],
  model: RenderModel,
  resolved: Readonly<Record<string, readonly [number, number]>>,
  pinned: Set<number>,
): void {
  for (const placement of model.besidePlacements ?? []) {
    if (pinned.has(placement.line)) continue;
    const point = besidePoint(placement, resolved);
    if (point === undefined) continue;
    paint(lines, placement.line, `${formatCoord(point[0])},${formatCoord(point[1])}!`);
    pinned.add(placement.line);
  }
}

function paint(lines: string[], lineIndex: number, rendered: string): void {
  const line = lines[lineIndex];
  if (line === undefined) {
    throw new ViewApplicationError(
      `render model statement line does not end a statement: ${pyStr("")}`,
    );
  }
  lines[lineIndex] = posStatementLine(line, rendered);
}

function copyLineKey(place: string, transition: string): string {
  // Same key as `copyKey` in render.ts. Kept here so view does not import render.
  return `${place}\0${transition}`;
}

function copyTarget(subject: string): readonly [string, string] | undefined {
  const marker = "@transition:";
  if (!subject.startsWith("place:") || !subject.includes(marker)) return undefined;
  const body = subject.slice("place:".length);
  const splitAt = body.indexOf(marker);
  if (splitAt <= 0) return undefined;
  const place = body.slice(0, splitAt);
  const transition = body.slice(splitAt + marker.length);
  if (!place || !transition) return undefined;
  return [place, transition];
}

function besidePoint(
  placement: BesidePlacement,
  resolved: Readonly<Record<string, readonly [number, number]>>,
): readonly [number, number] | undefined {
  const anchor = resolved[placement.anchor];
  const other = placement.also === undefined ? undefined : resolved[placement.also];
  if (placement.also !== undefined && anchor !== undefined && other !== undefined) {
    const fraction = (placement.betweenIndex + 1) / (placement.betweenCount + 1);
    return [
      anchor[0] + fraction * (other[0] - anchor[0]),
      anchor[1] + fraction * (other[1] - anchor[1]),
    ];
  }
  if (anchor !== undefined) return [anchor[0] + placement.slots * placement.gap, anchor[1]];
  if (other !== undefined && placement.alsoSlots !== undefined && placement.alsoGap !== undefined) {
    return [other[0] + placement.alsoSlots * placement.alsoGap, other[1]];
  }
  return undefined;
}

function formatCoord(value: number): string {
  return Number.isInteger(value) ? String(value) : String(value);
}

function posStatementLine(line: string, rendered: string): string {
  if (line.endsWith("];")) return `${line.slice(0, -2)}, pos="${rendered}"];`;
  if (line.endsWith(";")) return `${line.slice(0, -1)} [pos="${rendered}"];`;
  throw new ViewApplicationError(
    `render model statement line does not end a statement: ${pyStr(line)}`,
  );
}

function point(value: unknown, context: string): readonly [number, number] {
  if (!isRecord(value) || Object.keys(value).length !== 2 || !("x" in value) || !("y" in value)) {
    throw new ViewApplicationError(context);
  }
  const x = value.x;
  const y = value.y;
  if (!isFiniteNumber(x) || !isFiniteNumber(y)) throw new ViewApplicationError(context);
  return [x, y];
}

function validateSubject(subject: string, viewName: string): void {
  if (copyTarget(subject) !== undefined) return;
  const separator = subject.indexOf(":");
  const kind = separator === -1 ? subject : subject.slice(0, separator);
  const name = separator === -1 ? "" : subject.slice(separator + 1);
  if (!name || (kind !== "place" && kind !== "transition")) {
    throw new ViewApplicationError(
      `view ${pyStr(viewName)} has invalid view subject ${pyStr(subject)} (expected 'place:<name>', 'transition:<name>', or 'place:<name>@transition:<name>')`,
    );
  }
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function payloadOf(raw: unknown): Record<string, unknown> | undefined {
  if (!isRecord(raw) || !isRecord(raw.annotations)) return undefined;
  const payload = raw.annotations["petrinet.dsl/v1"];
  return isRecord(payload) ? payload : undefined;
}

function viewsOf(raw: unknown): Record<string, unknown> | undefined {
  const payload = payloadOf(raw);
  if (payload === undefined || !isRecord(payload.views)) return undefined;
  return payload.views;
}

function viewOf(raw: unknown, viewName: string): Record<string, unknown> | undefined {
  const views = viewsOf(raw);
  if (views === undefined) return undefined;
  const view = views[viewName];
  return isRecord(view) ? view : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function pyStr(value: string): string {
  if (!value.includes("'") && !value.includes("\\")) return `'${value}'`;
  return JSON.stringify(value);
}
