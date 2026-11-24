import type {Marking, Net, Token} from "@velocitron/engine";

import {FIRING, INJECTION, NET_REVISION, TRACE} from "./kinds.js";

/** One decoded event, in sequence order for one instance. */
export interface StoredEvent {
  readonly seq: number;
  readonly kind: string;
  readonly payload: Readonly<Record<string, unknown>>;
}

export type JournalRecordLike = Readonly<Record<string, unknown>>;

function isToken(value: unknown): value is Token {
  if (value === null || typeof value !== "object") return false;
  if (!("type" in value) || !("data" in value)) return false;
  const token = value as {type: unknown; data: unknown};
  return typeof token.type === "string" && token.data !== null && typeof token.data === "object" && !Array.isArray(token.data);
}

function tokenOf(value: unknown): Token {
  if (!isToken(value)) throw new TypeError("record token is missing type and data");
  return {type: value.type, data: value.data};
}

function deepEqual(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (typeof left !== "object" || typeof right !== "object" || left === null || right === null) return false;
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false;
    return left.every((item, index) => deepEqual(item, right[index]));
  }
  const leftKeys = Object.keys(left);
  const rightRecord = right as Record<string, unknown>;
  if (leftKeys.length !== Object.keys(rightRecord).length) return false;
  return leftKeys.every((key) => deepEqual((left as Record<string, unknown>)[key], rightRecord[key]));
}

function sameToken(left: Token, right: Token): boolean {
  return left.type === right.type && deepEqual(left.data, right.data);
}

function consumeSources(net: Net): Map<string, Set<string>> {
  const sources = new Map<string, Set<string>>();
  for (const arc of net.arcs) {
    if (!("consume" in arc)) continue;
    const consume = arc.consume;
    const place = arc.from.place;
    const transition = arc.to.transition;
    if (consume === undefined || consume.mode !== "consume") continue;
    if (place === undefined || transition === undefined) continue;
    const found = sources.get(transition);
    if (found === undefined) sources.set(transition, new Set([place]));
    else found.add(place);
  }
  return sources;
}

function removeTokens(marking: Marking, place: string, tokenDicts: readonly unknown[]): Marking {
  const remaining = [...(marking[place] ?? [])];
  for (const tokenDict of tokenDicts) {
    const target = tokenOf(tokenDict);
    const index = remaining.findIndex((existing) => sameToken(existing, target));
    if (index >= 0) remaining.splice(index, 1);
  }
  return {...marking, [place]: remaining};
}

function appendTokens(marking: Marking, place: string, tokens: readonly Token[]): Marking {
  return {...marking, [place]: [...(marking[place] ?? []), ...tokens]};
}

function asRecord(value: unknown): Record<string, unknown> {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError("journal record payload must be an object");
  }
  return value as Record<string, unknown>;
}

function replayEvent(marking: Marking, sources: ReadonlyMap<string, ReadonlySet<string>>, event: StoredEvent): Marking {
  if (event.kind === FIRING) {
    const record = event.payload;
    if (record.status !== "completed") return marking;
    const consumed = sources.get(String(record.transition)) ?? new Set<string>();
    const inputs = asRecord(record.inputTokens);
    for (const [place, tokenDicts] of Object.entries(inputs)) {
      if (consumed.has(place)) marking = removeTokens(marking, place, tokenDicts as readonly unknown[]);
    }
    const outputs = asRecord(record.outputTokens);
    for (const [place, tokenDicts] of Object.entries(outputs)) {
      marking = appendTokens(marking, place, (tokenDicts as readonly unknown[]).map(tokenOf));
    }
    return marking;
  }
  if (event.kind === INJECTION) {
    const record = event.payload;
    const tokens = (record.tokens as readonly unknown[]).map(tokenOf);
    if (record.kind === "update") return {...marking, [String(record.place)]: tokens};
    return appendTokens(marking, String(record.place), tokens);
  }
  // Deposit violations, net revisions, and traces carry no marking effect.
  return marking;
}

/** Rebuild a marking by applying recorded event effects. No handlers run. */
export function replayEvents(
  net: Net,
  events: readonly StoredEvent[],
  initial?: Marking,
): Marking {
  let marking: Marking = initial ?? net.initialMarking ?? {};
  const sources = consumeSources(net);
  for (const event of events) marking = replayEvent(marking, sources, event);
  return marking;
}

function ownInjectionKind(record: JournalRecordLike): "inject" | "update" {
  const kind = record.kind;
  if (kind === "inject" || kind === "update") return kind;
  const replaced = record.replaced;
  return Array.isArray(replaced) && replaced.length > 0 ? "update" : "inject";
}

function channelOf(record: JournalRecordLike): string {
  if ("event" in record) return TRACE;
  if ("injectionId" in record) return INJECTION;
  if ("firingId" in record) return FIRING;
  return NET_REVISION;
}

/**
 * Rebuild a marking from journal records.
 *
 * Classification matches the Python journal: ``event`` is a trace,
 * ``injectionId`` is an injection, ``firingId`` is a firing, and anything
 * else is a net revision. A durable row stores the channel name in ``kind``,
 * so an injection restores ``inject`` or ``update`` from ``replaced``.
 */
export function replayRecords(net: Net, records: readonly object[], initial?: Marking): Marking {
  const events: StoredEvent[] = records.map((record) => {
    const fields = record as JournalRecordLike;
    const kind = channelOf(fields);
    const payload: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(fields)) {
      if (key === "sequence" || key === "recorded_at") continue;
      if (kind !== INJECTION && key === "kind") continue;
      payload[key] = value;
    }
    if (kind === INJECTION) payload.kind = ownInjectionKind(fields);
    const rawSequence = payload.sequence;
    const sequence = typeof rawSequence === "number" && !Number.isNaN(rawSequence) ? rawSequence : 0;
    return {seq: sequence, kind, payload};
  });
  return replayEvents(net, events, initial);
}
