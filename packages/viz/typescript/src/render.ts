/**
 * Graphviz DOT for one already-built net.
 *
 * Port of the standalone-net path in `velocitron.viz`: places, ports,
 * transitions, consume and produce arcs, markings, fusion copies, and
 * beside rows. Composition diagrams, the feature legend, paired
 * walkthrough graphs, and per-token step marks stay in the Python
 * library. This module does not parse a document or install a console
 * script.
 */

import {renderCanonicalJson} from "./canonical.js";
import type {JsonValue, ReadonlyJsonObject} from "./schema/types.js";
import type {
  Arc,
  ConsumeArc,
  ConsumePattern,
  Marking,
  Net,
  Place,
  Port,
  Predicate,
  ProduceArc,
  ProduceTemplate,
  Token,
  Transition,
} from "./schema/types.js";
import {
  NAME_POINT,
  SMALL_POINT,
  besideGap,
  nodeWidth,
  type Decoration,
  type Decorations,
} from "./view.js";

const INPUT_PORT_FILL = "#e7f1fb";
const INPUT_PORT_BORDER = "#1f6feb";
const OUTPUT_PORT_FILL = "#fff3e0";
const OUTPUT_PORT_BORDER = "#b45309";
const TRANSITION_FILL = "lightyellow";
const GUARD_BORDER = "#7b2d8b";
const READ_COLOR = "#1f6feb";
const INHIBIT_COLOR = "crimson";
const MARKING_COLOR = "#1a7f37";
const MUTED = "#666666";
const FUSION_BORDER = "gray40";
const FUSION_FONT = "gray30";
const HIGHLIGHT_FILL = "#FFE08A";
const HIGHLIGHT_COLOR = "#D97706";
const NOTE_COLOR = "#0F766E";
const FAILURE_FILL = "#FDE2E1";
const FAILURE_COLOR = "#B42318";
const FADED_COLOR = "#9CA3AF";
const FADED_FILL = "#F3F4F6";
const EXPRESSION_WRAP = 60;
const SUMMARY_MAX = 48;
const TOKEN_GROUP_LIMIT = 8;
const TOKEN_TYPE_LIMIT = 64;
const TOKEN_DATA_LIMIT = 160;
const FIELD_LINE_CHARS = 48;
const GENERIC = "token";
const GRAPH_DEFAULTS = [
  '    node [fontname="Helvetica"];',
  '    edge [fontname="Helvetica", fontsize=10];',
];

export const DETAIL_LEVELS = ["full", "summary", "structure"] as const;
export type Detail = (typeof DETAIL_LEVELS)[number];

export interface RenderStyle {
  readonly htmlLabels?: boolean;
  readonly tooltips?: boolean;
  readonly detail?: Detail;
  readonly quietColors?: readonly string[];
  readonly shownFields?: Readonly<Record<string, readonly string[]>>;
}

export interface NetRenderOptions {
  readonly rankdir?: string;
  readonly includeMarking?: boolean;
  readonly marking?: Marking;
  readonly style?: RenderStyle;
  readonly renderFusion?: boolean;
  readonly decorations?: Decorations;
}

export interface BesidePlacement {
  readonly line: number;
  readonly place: string;
  readonly anchor: string;
  readonly slots: number;
  readonly gap: number;
  readonly also?: string;
  readonly alsoSlots?: number;
  readonly alsoGap?: number;
  readonly betweenIndex: number;
  readonly betweenCount: number;
}

export interface RenderModel {
  readonly dot: string;
  readonly nodeLines: Readonly<Record<string, readonly number[]>>;
  readonly arcLines: readonly number[];
  readonly graphAttrLine: number;
  readonly besideLines: readonly number[];
  readonly besidePlacements: readonly BesidePlacement[];
}

export interface FusionLayout {
  readonly copies: ReadonlyMap<string, string>;
  readonly rows: readonly (readonly string[])[];
}

export interface MarkingRow {
  readonly segments: readonly (readonly [string, boolean])[];
  readonly text: string;
}

const NO_DECORATION: Decoration = {};
const EMPTY_DECORATIONS: Decorations = {nodes: {}, arcs: {}, quietColors: [], shownFields: {}};

interface Style {
  readonly htmlLabels: boolean;
  readonly tooltips: boolean;
  readonly detail: Detail;
  readonly quietColors: ReadonlySet<string>;
  readonly shownFields: Readonly<Record<string, readonly string[]>>;
}

export function netToDot(net: Net, options: NetRenderOptions = {}): string {
  return netRenderModel(net, options).dot;
}

export function netRenderModel(net: Net, options: NetRenderOptions = {}): RenderModel {
  const style = styleOf(options.style);
  const rankdir = options.rankdir ?? "TB";
  const header = ["digraph net {", `    rankdir=${rankdir};`];
  if (net.name !== "unnamed") {
    const title = style.htmlLabels
      ? `label=<<b>${html(net.name)}</b>>; labelloc=t;`
      : `label="${dotString(net.name)}"; labelloc=t;`;
    header.push(`    ${title}`);
  }
  header.push(...GRAPH_DEFAULTS);
  const recorder = new RenderIndex(header.length + 1);
  const body = netBody(net, {
    includeMarking: options.includeMarking !== false,
    marking: options.marking,
    style,
    renderFusion: options.renderFusion !== false,
    decorations: options.decorations ?? EMPTY_DECORATIONS,
    recorder,
  });
  const dot = `${[...header, "", ...body, "}"].join("\n")}\n`;
  const nodeLines: Record<string, readonly number[]> = {};
  for (const [key, indexes] of recorder.nodeLines) nodeLines[key] = indexes;
  return {
    dot,
    nodeLines,
    arcLines: recorder.arcLines,
    graphAttrLine: header.length,
    besideLines: recorder.besideLines,
    besidePlacements: recorder.besidePlacements,
  };
}

export function siblingGroups(net: Net, fusion: ReadonlySet<string>): string[][] {
  const inputs = new Map<string, Set<string>>();
  const firstArcs: Array<readonly [string, string]> = [];
  for (const arc of net.arcs) {
    if (!isConsume(arc) || fusion.has(arc.from.place)) continue;
    const transition = arc.to.transition;
    const place = arc.from.place;
    let places = inputs.get(transition);
    if (places === undefined) {
      places = new Set();
      inputs.set(transition, places);
    }
    if (!places.has(place)) {
      places.add(place);
      firstArcs.push([place, transition]);
    }
  }
  const groups = new Map<string, string[]>();
  for (const [place, transition] of firstArcs) {
    const places = inputs.get(transition);
    if (places?.size === 1 && places.has(place)) {
      const group = groups.get(place);
      if (group === undefined) groups.set(place, [transition]);
      else group.push(transition);
    }
  }
  return [...groups.values()].filter((group) => group.length > 1);
}

export function fusionLayout(
  net: Net,
  fusion: ReadonlySet<string>,
  decorations: Decorations = EMPTY_DECORATIONS,
): FusionLayout {
  const instances = fusionInstances(net, fusion);
  const besideOf = (place: string): Decoration | undefined => {
    const decoration = decorations.nodes[`place:${place}`];
    return decoration?.beside === true ? decoration : undefined;
  };
  const besidePlaces = new Map<string, string[]>();
  for (const [place, transition] of instances) {
    if (besideOf(place) === undefined) continue;
    const list = besidePlaces.get(transition);
    if (list === undefined) besidePlaces.set(transition, [place]);
    else list.push(place);
  }
  const shared = new Map<string, string>();
  const gaps = new Map<string, string[]>();
  const outerRight = new Set<string>();
  const outwardLeft = new Set<string>();
  const outwardRight = new Set<string>();
  const segments: string[][] = [];
  for (const group of siblingGroups(net, fusion)) {
    const linked = Array.from({length: Math.max(group.length - 1, 0)}, () => false);
    const places = group.flatMap((transition) => besidePlaces.get(transition) ?? []);
    for (const place of unique(places)) {
      const decoration = besideOf(place);
      if (decoration === undefined || decoration.besideSide != null) continue;
      let start = 0;
      while (start < group.length) {
        let end = start;
        while (end < group.length && (besidePlaces.get(group[end]!) ?? []).includes(place)) end += 1;
        const run = group.slice(start, end);
        // Unshared (ADR 0068): one row, copies outside it. A missing
        // besideShare still shares, which is the ADR 0035 default.
        if (run.length > 1 && decoration.besideShare === false) {
          for (let index = start; index < end - 1; index += 1) linked[index] = true;
          outwardLeft.add(pairKey(place, run[0]!));
          outwardRight.add(pairKey(place, run[run.length - 1]!));
        } else {
          for (let index = 0; index < run.length - 1; index += 2) {
            const left = run[index]!;
            const right = run[index + 1]!;
            const copy = copyId(place, [left, right]);
            shared.set(pairKey(place, left), copy);
            shared.set(pairKey(place, right), copy);
            pushMap(gaps, edgeKey(left, right), place);
          }
          if (run.length > 1) {
            for (let index = start; index < end - 1; index += 1) linked[index] = true;
            if (run.length % 2 === 1) outerRight.add(pairKey(place, run[run.length - 1]!));
          }
        }
        start = end === start ? end + 1 : end;
      }
    }
    let first = 0;
    for (let index = 0; index < group.length; index += 1) {
      if (index === group.length - 1 || !linked[index]) {
        if (index > first) segments.push(group.slice(first, index + 1));
        first = index + 1;
      }
    }
  }
  const segmentOf = new Map<string, number>();
  segments.forEach((segment, index) => {
    for (const transition of segment) segmentOf.set(transition, index);
  });
  const row = (transitions: readonly string[]): string[] => {
    const order: string[] = [];
    for (let index = 0; index < transitions.length; index += 1) {
      const transition = transitions[index]!;
      const before = index > 0 ? transitions[index - 1] : undefined;
      const after = index + 1 < transitions.length ? transitions[index + 1] : undefined;
      const left: string[] = [];
      const right: string[] = [];
      const sharedLeft = before === undefined ? 0 : (gaps.get(edgeKey(before, transition))?.length ?? 0);
      const sharedRight = after === undefined ? 0 : (gaps.get(edgeKey(transition, after))?.length ?? 0);
      for (const place of besidePlaces.get(transition) ?? []) {
        if (shared.has(pairKey(place, transition))) continue;
        const decoration = besideOf(place);
        if (decoration === undefined) continue;
        const key = pairKey(place, transition);
        const side =
          decoration.besideSide != null
            ? decoration.besideSide
            : outwardLeft.has(key)
              ? "left"
              : outwardRight.has(key) || outerRight.has(key)
                ? "right"
                : left.length + sharedLeft <= right.length + sharedRight
                  ? "left"
                  : "right";
        (side === "left" ? left : right).push(copyId(place, [transition]));
      }
      order.push(...left.reverse(), transition, ...right);
      if (after !== undefined) {
        for (const place of gaps.get(edgeKey(transition, after)) ?? []) {
          order.push(copyId(place, [transition, after]));
        }
      }
    }
    return order;
  };
  const rows: string[][] = [];
  const seenRows = new Set<string>();
  for (const transition of besidePlaces.keys()) {
    const segment = segmentOf.get(transition);
    const key = segment === undefined ? `t:${transition}` : `s:${segment}`;
    if (seenRows.has(key)) continue;
    seenRows.add(key);
    rows.push(row(segment === undefined ? [transition] : segments[segment]!));
  }
  const copies = new Map<string, string>();
  for (const [place, transition] of instances) {
    copies.set(
      pairKey(place, transition),
      shared.get(pairKey(place, transition)) ?? copyId(place, [transition]),
    );
  }
  return {copies, rows};
}

export function besidePlacements(
  layout: FusionLayout,
  drawn: ReadonlyMap<string, {line: number; place: string}>,
  widths: ReadonlyMap<string, number>,
): BesidePlacement[] {
  // Keep this in step with `_beside_placements` in the Python renderer.
  const users = new Map<string, Set<string>>();
  const sideGap = (anchor: string, nodes: readonly string[]): number => {
    const widest = nodes.reduce((width, node) => Math.max(width, widths.get(node) ?? 0), 0);
    return besideGap(widths.get(anchor) ?? 0, widest);
  };
  for (const [key, copy] of layout.copies) {
    const transition = key.split("\0")[1];
    if (transition === undefined) continue;
    const found = users.get(copy);
    if (found === undefined) users.set(copy, new Set([transition]));
    else found.add(transition);
  }
  const placements: BesidePlacement[] = [];
  const own = (node: string, anchor: string, slots: number, gap: number): void => {
    const copy = drawn.get(node);
    if (copy === undefined) return;
    placements.push({
      line: copy.line,
      place: `place:${copy.place}`,
      anchor: `transition:${anchor}`,
      slots,
      gap,
      betweenIndex: 0,
      betweenCount: 1,
    });
  };
  for (const row of layout.rows) {
    const transAt = row.flatMap((node, index) => (drawn.has(node) ? [] : [index]));
    const first = transAt[0];
    const last = transAt[transAt.length - 1];
    if (first === undefined || last === undefined) continue;
    const leftNodes = row.slice(0, first).reverse();
    if (leftNodes.length > 0) {
      const gap = sideGap(row[first]!, leftNodes);
      leftNodes.forEach((node, index) => own(node, row[first]!, -(index + 1), gap));
    }
    const rightNodes = row.slice(last + 1);
    if (rightNodes.length > 0) {
      const gap = sideGap(row[last]!, rightNodes);
      rightNodes.forEach((node, index) => own(node, row[last]!, index + 1, gap));
    }
    for (let pair = 0; pair < transAt.length - 1; pair += 1) {
      const leftIndex = transAt[pair]!;
      const rightIndex = transAt[pair + 1]!;
      const leftName = row[leftIndex]!;
      const rightName = row[rightIndex]!;
      const ownRight: string[] = [];
      const ownLeft: string[] = [];
      const shared: string[] = [];
      for (const node of row.slice(leftIndex + 1, rightIndex)) {
        const used = users.get(node) ?? new Set<string>();
        if (used.has(leftName) && used.has(rightName)) shared.push(node);
        else if (used.has(rightName) && !used.has(leftName)) ownLeft.push(node);
        else ownRight.push(node);
      }
      const gapRight = ownRight.length + shared.length > 0 ? sideGap(leftName, [...ownRight, ...shared]) : 0;
      const gapLeft = ownLeft.length + shared.length > 0 ? sideGap(rightName, [...ownLeft, ...shared]) : 0;
      ownRight.forEach((node, index) => own(node, leftName, index + 1, gapRight));
      ownLeft
        .slice()
        .reverse()
        .forEach((node, index) => own(node, rightName, -(index + 1), gapLeft));
      shared.forEach((node, index) => {
        const copy = drawn.get(node);
        if (copy === undefined) return;
        placements.push({
          line: copy.line,
          place: `place:${copy.place}`,
          anchor: `transition:${leftName}`,
          slots: ownRight.length + index + 1,
          gap: gapRight,
          also: `transition:${rightName}`,
          alsoSlots: -(ownLeft.length + (shared.length - index)),
          alsoGap: gapLeft,
          betweenIndex: index,
          betweenCount: shared.length,
        });
      });
    }
  }
  return placements;
}

export function fusionCopy(
  layout: FusionLayout,
  place: string,
  transition: string,
): string | undefined {
  return layout.copies.get(pairKey(place, transition));
}

export function memberLabel(place: string, transition?: Transition): string {
  const members = place.split("__");
  if (transition !== undefined && transition.name.includes(".")) {
    const alias = transition.name.slice(0, transition.name.lastIndexOf("."));
    for (const [key, bound] of Object.entries(transition.bindingNames ?? {})) {
      if (bound === place) return `${alias}.${key}`;
    }
    for (const member of members) {
      const prefix = `${alias}.`;
      if (!member.startsWith(prefix)) continue;
      const local = member.slice(prefix.length);
      if (!local.includes(".")) return member;
    }
  }
  return members[0] ?? place;
}

export function markingRows(
  tokens: readonly Token[],
  shownFields: Readonly<Record<string, readonly string[]>> = {},
): MarkingRow[] {
  const groups = new Map<string, {type: string; segments: Array<readonly [string, boolean]>; count: number}>();
  for (const token of tokens) {
    const chosen = Object.prototype.hasOwnProperty.call(shownFields, token.type)
      ? shownFields[token.type]
      : undefined;
    const segments = tokenSegments(token, chosen);
    const key = `${token.type}\0${JSON.stringify(segments)}`;
    const existing = groups.get(key);
    if (existing === undefined) groups.set(key, {type: token.type, segments, count: 1});
    else existing.count += 1;
  }
  const sorted = [...groups.values()].sort((left, right) => {
    if (left.type < right.type) return -1;
    if (left.type > right.type) return 1;
    return compareSegments(left.segments, right.segments);
  });
  const rows: MarkingRow[] = [];
  for (let index = 0; index < sorted.length; index += 1) {
    if (index === TOKEN_GROUP_LIMIT) {
      const remaining = sorted.length - index;
      const suffix = remaining === 1 ? "group" : "groups";
      rows.push(markingRow([[`… + ${remaining} more token ${suffix}`, false]]));
      break;
    }
    const item = sorted[index]!;
    const displayType = item.type === GENERIC ? "" : ` ${truncate(item.type, TOKEN_TYPE_LIMIT)}`;
    const prefix = item.count === 1 ? "●" : `● × ${item.count}`;
    rows.push(markingRow([[`${prefix}${displayType}`, false], ...item.segments]));
  }
  return rows;
}

class RenderIndex {
  readonly nodeLines = new Map<string, number[]>();
  readonly arcLines: number[] = [];
  readonly besideLines: number[] = [];
  readonly besidePlacements: BesidePlacement[] = [];

  constructor(private readonly offset: number) {}

  recordNode(key: string, position: number): void {
    const found = this.nodeLines.get(key);
    if (found === undefined) this.nodeLines.set(key, [this.offset + position]);
    else found.push(this.offset + position);
  }

  recordArc(position: number): void {
    this.arcLines.push(this.offset + position);
  }

  recordBeside(position: number): void {
    this.besideLines.push(this.offset + position);
  }

  recordBesidePlacement(placement: BesidePlacement): void {
    this.besidePlacements.push({...placement, line: this.offset + placement.line});
  }
}

function netBody(
  net: Net,
  args: {
    includeMarking: boolean;
    marking: Marking | undefined;
    style: Style;
    renderFusion: boolean;
    decorations: Decorations;
    recorder: RenderIndex | undefined;
    indent?: string;
    prefix?: string;
  },
): string[] {
  const indent = args.indent ?? "    ";
  const prefix = args.prefix ?? "";
  const selected = !args.includeMarking
    ? undefined
    : (args.marking ?? net.initialMarking);
  const fusion = args.renderFusion
    ? new Set(net.places.filter(isFusionPlace).map((place) => place.name))
    : new Set<string>();
  const tokensOf = (place: Place): readonly Token[] => selected?.[place.name] ?? [];
  const nodeDecoration = (key: string): Decoration => args.decorations.nodes[key] ?? NO_DECORATION;
  const lines: string[] = [];
  const widths = new Map<string, number>();
  for (const place of net.places) {
    if (fusion.has(place.name)) continue;
    args.recorder?.recordNode(`place:${place.name}`, lines.length);
    const attrs = placeAttrs(place, tokensOf(place), {
      label: memberLabel(place.name),
      style: args.style,
      decoration: nodeDecoration(`place:${place.name}`),
    });
    lines.push(`${indent}${quote(`${prefix}${place.name}`)} [${attrs}];`);
  }
  lines.push("");
  for (const transition of net.transitions) {
    args.recorder?.recordNode(`transition:${transition.name}`, lines.length);
    const transitionDecoration = nodeDecoration(`transition:${transition.name}`);
    widths.set(transition.name, nodeWidth(measureTransition(transition, args.style, transitionDecoration)));
    const attrs = transitionAttrs(transition, args.style, transitionDecoration);
    lines.push(`${indent}${quote(`${prefix}${transition.name}`)} [${attrs}];`);
  }
  lines.push("");
  const layout = fusionLayout(net, fusion, args.decorations);
  const drawn = new Map<string, {line: number; place: string}>();
  if (fusion.size > 0) {
    const places = new Map(net.places.map((place) => [place.name, place]));
    const transitions = new Map(net.transitions.map((transition) => [transition.name, transition]));
    for (const [key, copy] of layout.copies) {
      if (drawn.has(copy)) continue;
      const [placeName, transitionName] = key.split("\0");
      const place = places.get(placeName!);
      if (place === undefined || placeName === undefined || transitionName === undefined) continue;
      args.recorder?.recordNode(`place:${placeName}`, lines.length);
      drawn.set(copy, {line: lines.length, place: placeName});
      const label = memberLabel(placeName, transitions.get(transitionName));
      widths.set(copy, nodeWidth(measurePlace(label, place, nodeDecoration(`place:${placeName}`))));
      const attrs = placeAttrs(place, tokensOf(place), {
        label,
        style: args.style,
        fusion: true,
        decoration: nodeDecoration(`place:${placeName}`),
      });
      lines.push(`${indent}${quote(`${prefix}${copy}`)} [${attrs}];`);
    }
    lines.push("");
  }
  if (args.recorder !== undefined) {
    for (const placement of besidePlacements(layout, drawn, widths)) {
      args.recorder.recordBesidePlacement(placement);
    }
  }
  const transitionNames = new Set(net.transitions.map((transition) => transition.name));
  const besideCopies = new Set<string>();
  for (const row of layout.rows) {
    for (const node of row) if (!transitionNames.has(node)) besideCopies.add(node);
  }
  net.arcs.forEach((arc, index) => {
    lines.push(
      arcEdge(arc, indent, prefix, args.style, layout.copies, besideCopies, args.decorations.arcs[index] ?? NO_DECORATION),
    );
    args.recorder?.recordArc(lines.length - 1);
  });
  for (const statement of besideStatements(layout, indent, prefix)) {
    args.recorder?.recordBeside(lines.length);
    lines.push(statement);
  }
  return lines;
}

function measurePlace(
  name: string,
  place: Place,
  decoration: Decoration,
): Array<readonly [string, number]> {
  const lines: Array<readonly [string, number]> = [[name, NAME_POINT]];
  const colors = place.accepts.filter((type) => type !== GENERIC);
  if (colors.length > 0) lines.push([`⟨${colors.join(", ")}⟩`, SMALL_POINT]);
  if (typeof decoration.highlightLabel === "string") lines.push([decoration.highlightLabel, SMALL_POINT]);
  if (typeof decoration.note === "string") lines.push([decoration.note, SMALL_POINT]);
  return lines;
}

function measureTransition(
  transition: Transition,
  style: Style,
  decoration: Decoration,
): Array<readonly [string, number]> {
  const lines: Array<readonly [string, number]> = [[transition.name, NAME_POINT]];
  if (decoration.faded === true) return lines;
  const summary = style.detail === "summary" && typeof decoration.summary === "string"
    ? decoration.summary
    : undefined;
  if (style.detail !== "structure") {
    if (transition.handler !== undefined) lines.push([`${transition.handler}()`, SMALL_POINT]);
    if (summary !== undefined) lines.push([summary, SMALL_POINT]);
    else if (transition.guard !== undefined) lines.push([`guard: ${transition.guard}?`, SMALL_POINT]);
    if (summary === undefined) {
      if (transition.timer !== undefined) lines.push([`timer: ${transition.timer.cel}`, SMALL_POINT]);
      if (transition.priority !== undefined) lines.push([`priority ${transition.priority}`, SMALL_POINT]);
    }
  }
  if (typeof decoration.highlightLabel === "string") lines.push([decoration.highlightLabel, SMALL_POINT]);
  if (typeof decoration.note === "string") lines.push([decoration.note, SMALL_POINT]);
  return lines;
}

function placeAttrs(
  place: Place,
  tokens: readonly Token[],
  args: {label: string; style: Style; fusion?: boolean; decoration: Decoration},
): string {
  const accepted = place.accepts.filter((type) => type !== GENERIC);
  const lines = args.style.htmlLabels
    ? [`<b>${html(args.label)}</b>`]
    : [args.label];
  if (accepted.length > 0) {
    lines.push(
      args.style.htmlLabels
        ? `<font point-size="9" color="${MUTED}">&#10216;${html(accepted.join(", "))}&#10217;</font>`
        : `⟨${accepted.join(", ")}⟩`,
    );
  }
  if (place.port !== undefined) lines.push(portLine(place.port, args.style));
  lines.push(...decorationLines(args.decoration, args.style));
  lines.push(...markingLines(tokens, args.style));
  let attrs = `shape=ellipse, ${labelAttr(lines, args.style)}`;
  if (args.fusion === true) {
    attrs += `, class="fusion", style=dashed, color="${FUSION_BORDER}", fontcolor="${FUSION_FONT}"`;
  } else if (place.port !== undefined) {
    const [fill, border] = place.port.direction === "input"
      ? [INPUT_PORT_FILL, INPUT_PORT_BORDER]
      : [OUTPUT_PORT_FILL, OUTPUT_PORT_BORDER];
    attrs += `, peripheries=2, style=filled, fillcolor="${fill}", color="${border}"`;
  }
  if (args.decoration.highlight === true) {
    const fillStyle = args.fusion === true ? '"dashed,filled"' : "filled";
    attrs += `, style=${fillStyle}, fillcolor="${HIGHLIGHT_FILL}", color="${HIGHLIGHT_COLOR}", penwidth=2`;
  }
  const tooltip = [place.description, tokensTooltip(tokens)].filter((item) => item).join("\n\n");
  return attrs + tooltipAttr(tooltip, args.style);
}

function transitionAttrs(transition: Transition, style: Style, decoration: Decoration): string {
  const name = transition.name;
  if (decoration.faded === true) {
    const text = style.htmlLabels ? `<b>${html(name)}</b>` : name;
    return (
      `shape=box, style="filled,dashed", fillcolor="${FADED_FILL}", color="${FADED_COLOR}", fontcolor="${FADED_COLOR}", ` +
      labelAttr([text], style) +
      tooltipAttr(transition.description, style)
    );
  }
  const lines = [style.htmlLabels ? `<b>${html(name)}</b>` : name];
  const summary = summaryLine(decoration, style);
  if (style.detail !== "structure") {
    if (transition.handler !== undefined) lines.push(small(`${escapeText(transition.handler, style)}()`, MUTED, style));
    if (summary !== undefined) lines.push(summary);
    if (transition.guard !== undefined && summary === undefined) {
      lines.push(small(`guard: ${escapeText(transition.guard, style)}?`, GUARD_BORDER, style));
    }
    if (transition.timer !== undefined && summary === undefined) {
      lines.push(small(`timer: ${expressionText(transition.timer.cel, style)}`, MUTED, style));
    }
    if (transition.priority !== undefined && summary === undefined) {
      lines.push(small(`priority ${transition.priority}`, MUTED, style));
    }
  }
  lines.push(...decorationLines(decoration, style));
  let attrs = `shape=box, style=filled, fillcolor=${TRANSITION_FILL}, ${labelAttr(lines, style)}`;
  if (transition.guard !== undefined) attrs += `, color="${GUARD_BORDER}", penwidth=1.6`;
  if (decoration.failure === true) {
    attrs += `, fillcolor="${FAILURE_FILL}", color="${FAILURE_COLOR}", penwidth=2.5`;
  } else if (decoration.highlight === true) {
    attrs += `, fillcolor="${HIGHLIGHT_FILL}", color="${HIGHLIGHT_COLOR}", penwidth=2`;
  }
  return attrs + tooltipAttr(transition.description, style);
}

function arcEdge(
  arc: Arc,
  indent: string,
  prefix: string,
  style: Style,
  copies: ReadonlyMap<string, string>,
  besideCopies: ReadonlySet<string>,
  decoration: Decoration,
): string {
  let source: string;
  let target: string;
  let attrs: string;
  let placeNode: string;
  let dashed = false;
  let inhibit = false;
  if (isConsume(arc)) {
    const fromPlace = copies.get(pairKey(arc.from.place, arc.to.transition)) ?? arc.from.place;
    source = quote(`${prefix}${fromPlace}`);
    target = quote(`${prefix}${arc.to.transition}`);
    attrs = consumeEdgeAttrs(arc.consume, arc.description, style, decoration);
    placeNode = fromPlace;
    dashed = arc.consume.mode !== "consume";
    inhibit = arc.consume.mode === "inhibit";
  } else {
    const toPlace = copies.get(pairKey(arc.to.place, arc.from.transition)) ?? arc.to.place;
    source = quote(`${prefix}${arc.from.transition}`);
    target = quote(`${prefix}${toPlace}`);
    attrs = produceEdgeAttrs(arc.produce, arc.description, style, decoration);
    placeNode = toPlace;
  }
  if (decoration.faded === true) {
    attrs = `color="${FADED_COLOR}"${dashed ? ", style=dashed" : ""}${inhibit ? ", arrowhead=odot" : ""}`;
  }
  if (besideCopies.has(placeNode)) attrs = attrs ? `${attrs}, constraint=false` : "constraint=false";
  if (!attrs) return `${indent}${source} -> ${target};`;
  return `${indent}${source} -> ${target} [${attrs}];`;
}

function consumeEdgeAttrs(
  pattern: ConsumePattern,
  description: string | undefined,
  style: Style,
  decoration: Decoration,
): string {
  const times = style.htmlLabels ? "&#215;" : "×";
  const generic = pattern.type === GENERIC;
  const hidden = generic || (pattern.mode === "consume" && style.quietColors.has(pattern.type));
  const weight = pattern.weight === 1 ? "" : `${pattern.weight} ${times} `;
  const type = hidden ? "" : style.htmlLabels ? html(pattern.type) : pattern.type;
  let head: string;
  let edgeStyle = "";
  if (pattern.mode === "inhibit") {
    head = generic ? "no" : `no ${type}`;
    edgeStyle = `arrowhead=odot, color="${INHIBIT_COLOR}", style=dashed`;
    if (style.htmlLabels) head = `<font color="${INHIBIT_COLOR}">${head}</font>`;
  } else if (pattern.mode === "read") {
    head = `read ${weight}${type}`.trimEnd();
    edgeStyle = `color="${READ_COLOR}", style=dashed`;
    if (style.htmlLabels) head = `<font color="${READ_COLOR}">${head}</font>`;
  } else {
    head = `${weight}${type}`.trimEnd();
  }
  if (style.htmlLabels && head) head = `<font point-size="10">${head}</font>`;
  const lines = head ? [head] : [];
  const summary = summaryLine(decoration, style);
  if (summary !== undefined) lines.push(summary);
  else if (style.detail !== "structure") {
    if (pattern.predicate !== undefined) lines.push(predicateLine(pattern.predicate, style));
    if (pattern.correlate !== undefined) {
      lines.push(small(expressionText(pattern.correlate.cel, style), MUTED, style, true));
    }
  }
  lines.push(...decorationLines(decoration, style));
  let attrs = lines.length > 0 ? labelAttr(lines, style) : "";
  if (edgeStyle) attrs = attrs ? `${attrs}, ${edgeStyle}` : edgeStyle;
  attrs = highlightEdge(attrs, decoration);
  const tooltip = tooltipAttr(description, style);
  return attrs ? attrs + tooltip : tooltip.replace(/^, /, "");
}

function produceEdgeAttrs(
  template: ProduceTemplate,
  description: string | undefined,
  style: Style,
  decoration: Decoration,
): string {
  const lines: string[] = [];
  if (template.type !== GENERIC && !style.quietColors.has(template.type)) {
    lines.push(style.htmlLabels ? `<font point-size="10">${html(template.type)}</font>` : template.type);
  }
  const summary = summaryLine(decoration, style);
  if (summary !== undefined) lines.push(summary);
  else if (style.detail !== "structure") {
    if (template.data !== undefined) {
      lines.push(small(expressionText(`+ data ${pythonJson(template.data)}`, style), MUTED, style, true));
    } else if (template.cel !== undefined) {
      lines.push(small(expressionText(`+ data cel ${template.cel}`, style), MUTED, style, true));
    }
  }
  lines.push(...decorationLines(decoration, style));
  const attrs = highlightEdge(lines.length > 0 ? labelAttr(lines, style) : "", decoration);
  const tooltip = tooltipAttr(description, style);
  return attrs ? attrs + tooltip : tooltip.replace(/^, /, "");
}

function decorationLines(decoration: Decoration, style: Style): string[] {
  const lines: string[] = [];
  if (typeof decoration.highlightLabel === "string") {
    const label = escapeText(decoration.highlightLabel, style);
    const color = decoration.failure === true ? FAILURE_COLOR : HIGHLIGHT_COLOR;
    lines.push(style.htmlLabels ? `<font point-size="9" color="${color}"><b>${label}</b></font>` : label);
  }
  if (typeof decoration.note === "string") {
    lines.push(small(wrappedText(decoration.note, style), NOTE_COLOR, style, true));
  }
  return lines;
}

function summaryLine(decoration: Decoration, style: Style): string | undefined {
  if (style.detail !== "summary" || typeof decoration.summary !== "string") return undefined;
  return small(wrappedText(decoration.summary, style), MUTED, style, true);
}

function markingLines(tokens: readonly Token[], style: Style): string[] {
  const rows = markingRows(tokens, style.shownFields);
  if (rows.length === 0) return [];
  if (!style.htmlLabels) return rows.map((row) => row.text);
  const htmlRows = rows
    .map((row) => {
      const text = row.segments.map(([part]) => html(part).replaceAll("\n", "<br/>")).join("");
      return `<tr><td align="left"><font point-size="9" color="${MARKING_COLOR}">${text}</font></td></tr>`;
    })
    .join("");
  return [
    `<table border="1" cellborder="0" cellspacing="0" cellpadding="4" style="rounded" color="${MARKING_COLOR}">${htmlRows}</table>`,
  ];
}

function tokenSegments(
  token: Token,
  fields: readonly string[] | undefined,
): Array<readonly [string, boolean]> {
  if (fields === undefined) {
    const canonical = renderCanonicalJson(token.data);
    if (canonical === "{}") return [];
    return [[` ${breakAfterCommas(truncate(canonical, TOKEN_DATA_LIMIT))}`, false]];
  }
  const parts: Array<readonly [string, boolean]> = [];
  for (const path of fields) {
    const found = fieldValue(token.data, path);
    if (found.present) parts.push([`${path}=${fieldText(found.value)}`, false]);
  }
  if (parts.length === 0) return [[" …", false]];
  const segments: Array<readonly [string, boolean]> = [];
  let width = 0;
  parts.forEach(([text], index) => {
    let separator: string;
    if (index === 0) separator = " ";
    else if (width + text.length + 3 > FIELD_LINE_CHARS) {
      separator = "\n";
      width = 0;
    } else separator = " · ";
    segments.push([separator, false], [text, false]);
    width += separator.length + text.length;
  });
  return segments;
}

function besideStatements(layout: FusionLayout, indent: string, prefix: string): string[] {
  if (layout.rows.length === 0) return [];
  const statements = [`${indent}newrank=true;`, `${indent}remincross=false;`];
  layout.rows.forEach((row, index) => {
    const order = row.map((node) => quote(`${prefix}${node}`));
    statements.push(
      `${indent}subgraph "cluster_${prefix}beside_${index}" { label=""; peripheries=0; margin=0; { rank=same; ${order.join("; ")}; } }`,
    );
    statements.push(`${indent}${order.join(" -> ")} [style=invis];`);
  });
  return statements;
}

function fusionInstances(net: Net, fusion: ReadonlySet<string>): Array<readonly [string, string]> {
  const pairs: Array<readonly [string, string]> = [];
  const seen = new Set<string>();
  for (const arc of net.arcs) {
    const pair = isConsume(arc) && fusion.has(arc.from.place)
      ? ([arc.from.place, arc.to.transition] as const)
      : isProduce(arc) && fusion.has(arc.to.place)
        ? ([arc.to.place, arc.from.transition] as const)
        : undefined;
    if (pair === undefined || seen.has(pairKey(pair[0], pair[1]))) continue;
    seen.add(pairKey(pair[0], pair[1]));
    pairs.push(pair);
  }
  return pairs;
}

function styleOf(style: RenderStyle | undefined): Style {
  return {
    htmlLabels: style?.htmlLabels ?? true,
    tooltips: style?.tooltips ?? true,
    detail: style?.detail ?? "full",
    quietColors: new Set(style?.quietColors ?? []),
    shownFields: style?.shownFields ?? {},
  };
}

function isFusionPlace(place: Place): boolean {
  return pythonTruthy(place.annotations?.fusion);
}

function pythonTruthy(value: JsonValue | undefined): boolean {
  if (value === undefined || value === null || value === false || value === "" || value === 0) return false;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === "object") return Object.keys(value).length > 0;
  return true;
}

function isConsume(arc: Arc): arc is ConsumeArc {
  return "consume" in arc;
}

function isProduce(arc: Arc): arc is ProduceArc {
  return "produce" in arc;
}

function copyId(place: string, transitions: readonly string[]): string {
  return `${place}@${transitions.join("+")}`;
}

function pairKey(place: string, transition: string): string {
  return `${place}\0${transition}`;
}

function edgeKey(left: string, right: string): string {
  return `${left}\0${right}`;
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values)];
}

function pushMap(map: Map<string, string[]>, key: string, value: string): void {
  const found = map.get(key);
  if (found === undefined) map.set(key, [value]);
  else found.push(value);
}

function quote(identifier: string): string {
  return `"${identifier.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

function dotString(text: string): string {
  return text.replaceAll("\\", "\\\\").replaceAll('"', '\\"').replaceAll("\n", "\\n");
}

function html(text: string): string {
  return text.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
}

function escapeText(text: string, style: Style): string {
  return style.htmlLabels ? html(text) : text;
}

function truncate(text: string, limit: number): string {
  return text.length <= limit ? text : `${text.slice(0, limit - 1)}…`;
}

function expressionText(text: string, style: Style): string {
  if (style.detail === "summary") return escapeText(truncate(text, SUMMARY_MAX), style);
  return wrappedText(text, style);
}

function wrappedText(text: string, style: Style): string {
  const rows = wrapText(text, EXPRESSION_WRAP);
  const separator = style.htmlLabels ? "<br/>" : "\n";
  return rows.map((row) => escapeText(row, style)).join(separator);
}

function wrapText(text: string, width: number): string[] {
  if (text.length <= width) return [text];
  const rows: string[] = [];
  let rest = text;
  while (rest.length > width) {
    let breakAt = rest.lastIndexOf(" ", width);
    if (breakAt <= 0) {
      const next = rest.indexOf(" ");
      if (next === -1) {
        rows.push(rest);
        return rows;
      }
      breakAt = next;
    }
    rows.push(rest.slice(0, breakAt));
    rest = rest.slice(breakAt + 1);
  }
  if (rest.length > 0) rows.push(rest);
  return rows.length > 0 ? rows : [text];
}

function small(text: string, color: string, style: Style, italic = false): string {
  if (!style.htmlLabels) return text;
  const body = italic ? `<i>${text}</i>` : text;
  return `<font point-size="9" color="${color}">${body}</font>`;
}

function labelAttr(lines: readonly string[], style: Style): string {
  if (!style.htmlLabels) return `label="${dotString(lines.join("\n"))}"`;
  if (!lines.some((line) => line.startsWith("<table"))) return `label=<${lines.join("<br/>")}>`;
  const cells = lines.map((line) => `<tr><td align="center">${line}</td></tr>`).join("");
  return `label=<<table border="0" cellborder="0" cellspacing="0" cellpadding="0">${cells}</table>>`;
}

function tooltipAttr(description: string | undefined, style: Style): string {
  if (!description || !style.tooltips) return "";
  return `, tooltip="${dotString(description)}"`;
}

function portLine(port: Port, style: Style): string {
  if (!style.htmlLabels) {
    const suffix = port.type === GENERIC ? "" : ` · ${port.type}`;
    return `port ${port.direction}${suffix}`;
  }
  const color = port.direction === "input" ? INPUT_PORT_BORDER : OUTPUT_PORT_BORDER;
  const suffix = port.type === GENERIC ? "" : ` &#183; ${html(port.type)}`;
  return `<font point-size="9" color="${color}">port ${port.direction}${suffix}</font>`;
}

function predicateLine(predicate: Predicate, style: Style): string {
  const text =
    predicate.cel !== undefined
      ? expressionText(predicate.cel, style)
      : escapeText(`pred: ${predicate.handler}`, style);
  return small(text, MUTED, style, true);
}

function highlightEdge(attrs: string, decoration: Decoration): string {
  if (decoration.highlight !== true) return attrs;
  const highlight = `color="${HIGHLIGHT_COLOR}", penwidth=2.5`;
  return attrs ? `${attrs}, ${highlight}` : highlight;
}

function tokensTooltip(tokens: readonly Token[]): string {
  return tokens
    .map((token) => {
      const canonical = renderCanonicalJson(token.data);
      return token.type === GENERIC ? canonical : `${token.type} ${canonical}`;
    })
    .join("\n");
}

function isJsonObject(value: JsonValue): value is ReadonlyJsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function fieldValue(data: JsonValue, path: string): {present: boolean; value: JsonValue} {
  let value: JsonValue = data;
  for (const key of path.split(".")) {
    if (!isJsonObject(value) || !(key in value)) return {present: false, value: null};
    value = value[key]!;
  }
  return {present: true, value};
}

function fieldText(value: JsonValue): string {
  if (typeof value === "string" && value.length > 0 && !value.includes(",")) return value;
  return renderCanonicalJson(value);
}

function breakAfterCommas(text: string): string {
  let inString = false;
  let escaped = false;
  let result = "";
  for (const char of text) {
    result += char;
    if (escaped) escaped = false;
    else if (char === "\\" && inString) escaped = true;
    else if (char === '"') inString = !inString;
    else if (char === "," && !inString) result += "\n";
  }
  return result;
}

function markingRow(segments: ReadonlyArray<readonly [string, boolean]>): MarkingRow {
  return {segments, text: segments.map(([text]) => text).join("")};
}

function compareSegments(
  left: readonly (readonly [string, boolean])[],
  right: readonly (readonly [string, boolean])[],
): number {
  const count = Math.min(left.length, right.length);
  for (let index = 0; index < count; index += 1) {
    const [leftText, leftMark] = left[index]!;
    const [rightText, rightMark] = right[index]!;
    if (leftText < rightText) return -1;
    if (leftText > rightText) return 1;
    if (leftMark !== rightMark) return leftMark ? 1 : -1;
  }
  return left.length - right.length;
}

function pythonJson(value: JsonValue): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("not a JSON number");
    return Object.is(value, -0) ? "0" : String(value);
  }
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => pythonJson(item)).join(", ")}]`;
  if (!isJsonObject(value)) throw new TypeError("not a JSON object");
  return `{${Object.keys(value)
    .map((key) => `${JSON.stringify(key)}: ${pythonJson(value[key]!)}`)
    .join(", ")}}`;
}
