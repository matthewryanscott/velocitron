/**
 * Intended waits: cases of a choice where the token waits on purpose.
 *
 * A transition annotated `wait` names the cases in which no way out is
 * enabled on purpose. `when` is CEL over `binding`. `for` says what the
 * token waits for. The engine ignores the annotation.
 */

import {createDefaultCelAdapter, type CelAdapter} from "@velocitron/cel";
import type {Net, ReadonlyJsonObject, Token, Transition} from "@velocitron/engine";

export const WAIT_KEY = "wait";

export interface Wait {
  readonly transition: string;
  readonly when: string;
  readonly reason: string;
}

function shape(value: unknown): Array<readonly [string, string]> | null {
  const entries = Array.isArray(value) ? value : [value];
  if (entries.length === 0) return null;
  const found: Array<readonly [string, string]> = [];
  for (const entry of entries) {
    if (typeof entry !== "object" || entry === null || Array.isArray(entry)) return null;
    const fields = entry as Record<string, unknown>;
    const keys = Object.keys(fields);
    if (keys.length !== 2 || !keys.includes("when") || !keys.includes("for")) return null;
    const when = fields.when;
    const reason = fields.for;
    if (typeof when !== "string" || when.length === 0) return null;
    if (typeof reason !== "string" || reason.length === 0) return null;
    found.push([when, reason]);
  }
  return found;
}

/** The transition's intended waits. A malformed `wait` declares none. */
export function intendedWaits(transition: Transition): Wait[] {
  const found = shape(transition.annotations?.[WAIT_KEY]);
  return (found ?? []).map(([when, reason]) => ({transition: transition.name, when, reason}));
}

let defaultAdapter: CelAdapter | undefined;

function adapterOrDefault(adapter: CelAdapter | undefined): CelAdapter {
  if (adapter !== undefined) return adapter;
  defaultAdapter ??= createDefaultCelAdapter();
  return defaultAdapter;
}

/**
 * Whether the wait's condition is true for these tokens.
 *
 * A condition that fails to evaluate, or gives anything but `true`, does
 * not hold.
 */
export function holds(
  wait: Wait,
  keys: Readonly<Record<string, string>>,
  tokens: Readonly<Record<string, readonly Token[]>>,
  adapter?: CelAdapter,
): boolean {
  const chosen = adapterOrDefault(adapter);
  const binding: Record<string, unknown[]> = {};
  for (const [key, place] of Object.entries(keys)) {
    binding[key] = (tokens[place] ?? []).map((token) => token.data);
  }
  try {
    const context = {binding} as unknown as ReadonlyJsonObject;
    return chosen.evaluate(chosen.compile(wait.when), context) === true;
  } catch {
    return false;
  }
}

/** What is wrong with the `wait` annotations, in transition order. */
export function waitProblems(
  net: Net,
  adapter?: CelAdapter,
): Array<{readonly transition: string; readonly message: string}> {
  const problems: Array<{transition: string; message: string}> = [];
  const chosen = adapterOrDefault(adapter);
  for (const transition of net.transitions) {
    const value = transition.annotations?.[WAIT_KEY];
    if (value === undefined) continue;
    const found = shape(value);
    if (found === null) {
      problems.push({
        transition: transition.name,
        message: `the wait of [${transition.name}] must be {"when": "<CEL>", "for": "<what it waits for>"}, or a list of them`,
      });
      continue;
    }
    for (const [when] of found) {
      try {
        chosen.compile(when);
      } catch (error) {
        const detail = error instanceof Error ? error.message : String(error);
        problems.push({
          transition: transition.name,
          message: `the wait of [${transition.name}] is not valid CEL: ${detail}`,
        });
      }
    }
  }
  return problems;
}
