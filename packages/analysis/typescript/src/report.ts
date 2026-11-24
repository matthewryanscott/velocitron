/**
 * Read a proof report document.
 *
 * The JSON shape is the contract in `packages/spec/proofs.md`. This module
 * checks that shape. It does not explore a net, compile CEL, or lint.
 * The prover is the Python package `velocitron_analysis`.
 */

export const FACTS = ["choice", "invariants", "soundness", "refinement"] as const;

/** A fact name passed to `prove` in Python. A stored fact uses `invariant`. */
export type RequestedFact = (typeof FACTS)[number];

export const REPORT_VERSION = 1;

export type ProofStatus = "proved" | "refuted" | "unknown";

export type StoredFact = "choice" | "invariant" | "soundness" | "refinement";

export interface ProofToken {
  readonly type: string;
  readonly data: Readonly<Record<string, unknown>>;
}

export interface ProofMove {
  readonly kind: "fire" | "inject" | "update" | "advance";
  readonly transition?: string;
  readonly place?: string;
  readonly token?: ProofToken;
  readonly binding?: Readonly<Record<string, readonly ProofToken[]>>;
  readonly outputs?: Readonly<Record<string, readonly ProofToken[]>>;
}

export interface ProofFinding {
  readonly kind: string;
  readonly summary: string;
  readonly witness?: Readonly<Record<string, readonly ProofToken[]>>;
  readonly cases?: Readonly<Record<string, unknown>>;
  readonly count?: number;
  readonly enabled?: readonly string[];
  readonly transition?: string;
  readonly path?: readonly ProofMove[];
  readonly cycle?: readonly ProofMove[];
  readonly marking?: Readonly<Record<string, readonly ProofToken[]>>;
  readonly play?: string;
}

export interface ProofFact {
  readonly fact: StoredFact;
  readonly subject: string;
  readonly status: ProofStatus;
  readonly statement: string;
  readonly reason?: string;
  readonly assumptions?: readonly string[];
  readonly details?: Readonly<Record<string, unknown>>;
  readonly findings: readonly ProofFinding[];
}

export interface ProofReportDocument {
  readonly version: typeof REPORT_VERSION;
  readonly tool: string;
  readonly net: string;
  readonly source: string | null;
  readonly status: ProofStatus;
  readonly facts: readonly ProofFact[];
  readonly model: Readonly<Record<string, unknown>>;
  readonly exploration?: Readonly<Record<string, unknown>>;
  readonly composition?: Readonly<Record<string, unknown>>;
}

export class ProofReportError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ProofReportError";
  }
}

const STATUSES: ReadonlySet<string> = new Set(["proved", "refuted", "unknown"]);
const STORED_FACTS: ReadonlySet<string> = new Set([
  "choice",
  "invariant",
  "soundness",
  "refinement",
]);
const MOVE_KINDS: ReadonlySet<string> = new Set(["fire", "inject", "update", "advance"]);

function fail(message: string): never {
  throw new ProofReportError(message);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asStatus(value: unknown, where: string): ProofStatus {
  if (typeof value === "string" && STATUSES.has(value)) return value as ProofStatus;
  return fail(`${where} status must be proved, refuted, or unknown`);
}

function asToken(value: unknown, where: string): ProofToken {
  if (!isRecord(value) || typeof value.type !== "string" || !isRecord(value.data)) {
    return fail(`${where} token must have a type and a data object`);
  }
  return {type: value.type, data: value.data};
}

function asTokenList(value: unknown, where: string): readonly ProofToken[] {
  if (!Array.isArray(value)) return fail(`${where} must be a list of tokens`);
  return value.map((item, index) => asToken(item, `${where}[${index}]`));
}

function asMarking(
  value: unknown,
  where: string,
): Readonly<Record<string, readonly ProofToken[]>> {
  if (!isRecord(value)) return fail(`${where} must be a marking`);
  const found: Record<string, readonly ProofToken[]> = {};
  for (const [place, tokens] of Object.entries(value)) {
    found[place] = asTokenList(tokens, `${where}.${place}`);
  }
  return found;
}

function asString(value: unknown, where: string): string {
  if (typeof value !== "string") return fail(`${where} must be a string`);
  return value;
}

function asMove(value: unknown, where: string): ProofMove {
  if (!isRecord(value) || typeof value.kind !== "string" || !MOVE_KINDS.has(value.kind)) {
    return fail(`${where} kind must be fire, inject, update, or advance`);
  }
  return {
    kind: value.kind as ProofMove["kind"],
    ...(value.transition === undefined ? {} : {transition: asString(value.transition, `${where}.transition`)}),
    ...(value.place === undefined ? {} : {place: asString(value.place, `${where}.place`)}),
    ...(value.token === undefined ? {} : {token: asToken(value.token, `${where}.token`)}),
    ...(value.binding === undefined ? {} : {binding: asMarking(value.binding, `${where}.binding`)}),
    ...(value.outputs === undefined ? {} : {outputs: asMarking(value.outputs, `${where}.outputs`)}),
  };
}

function asMoves(value: unknown, where: string): readonly ProofMove[] {
  if (!Array.isArray(value)) return fail(`${where} must be a list of moves`);
  return value.map((step, index) => asMove(step, `${where}[${index}]`));
}

function asFinding(value: unknown, where: string): ProofFinding {
  if (!isRecord(value) || typeof value.kind !== "string" || typeof value.summary !== "string") {
    return fail(`${where} needs a kind and a summary`);
  }
  const enabled = value.enabled;
  if (
    enabled !== undefined &&
    (!Array.isArray(enabled) || enabled.some((name) => typeof name !== "string"))
  ) {
    return fail(`${where}.enabled must be a list of names`);
  }
  return {
    kind: value.kind,
    summary: value.summary,
    ...(value.witness === undefined ? {} : {witness: asMarking(value.witness, `${where}.witness`)}),
    ...(value.cases === undefined
      ? {}
      : {cases: isRecord(value.cases) ? value.cases : fail(`${where}.cases must be an object`)}),
    ...(value.count === undefined
      ? {}
      : {count: typeof value.count === "number" ? value.count : fail(`${where}.count must be a number`)}),
    ...(enabled === undefined ? {} : {enabled: enabled as readonly string[]}),
    ...(value.transition === undefined
      ? {}
      : {transition: asString(value.transition, `${where}.transition`)}),
    ...(value.path === undefined ? {} : {path: asMoves(value.path, `${where}.path`)}),
    ...(value.cycle === undefined ? {} : {cycle: asMoves(value.cycle, `${where}.cycle`)}),
    ...(value.marking === undefined ? {} : {marking: asMarking(value.marking, `${where}.marking`)}),
    ...(value.play === undefined ? {} : {play: asString(value.play, `${where}.play`)}),
  };
}

function asAssumptions(value: unknown, where: string): readonly string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    return fail(`${where} must be a list of strings`);
  }
  return value as readonly string[];
}

function asFact(value: unknown, index: number): ProofFact {
  const where = `facts[${index}]`;
  if (!isRecord(value)) return fail(`${where} must be an object`);
  if (typeof value.fact !== "string" || !STORED_FACTS.has(value.fact)) {
    return fail(`${where}.fact must be choice, invariant, soundness, or refinement`);
  }
  if (typeof value.subject !== "string" || typeof value.statement !== "string") {
    return fail(`${where} needs a subject and a statement`);
  }
  if (!Array.isArray(value.findings)) return fail(`${where}.findings must be a list`);
  return {
    fact: value.fact as StoredFact,
    subject: value.subject,
    status: asStatus(value.status, where),
    statement: value.statement,
    findings: value.findings.map((item, findingIndex) =>
      asFinding(item, `${where}.findings[${findingIndex}]`),
    ),
    ...(value.reason === undefined ? {} : {reason: asString(value.reason, `${where}.reason`)}),
    ...(value.assumptions === undefined
      ? {}
      : {assumptions: asAssumptions(value.assumptions, `${where}.assumptions`)}),
    ...(value.details === undefined
      ? {}
      : {
          details: isRecord(value.details)
            ? value.details
            : fail(`${where}.details must be an object`),
        }),
  };
}

/**
 * The report status: refuted if any fact is, otherwise unknown if any is,
 * otherwise proved. This is the rule in `packages/spec/proofs.md`.
 */
export function proofReportStatus(facts: readonly Pick<ProofFact, "status">[]): ProofStatus {
  if (facts.some((item) => item.status === "refuted")) return "refuted";
  if (facts.some((item) => item.status === "unknown")) return "unknown";
  return "proved";
}

/** Check a proof-report document and return it. Throws `ProofReportError`. */
export function readProofReport(value: unknown): ProofReportDocument {
  if (!isRecord(value)) return fail("a proof report is a JSON object");
  if (value.version !== REPORT_VERSION) return fail(`proof report version must be ${REPORT_VERSION}`);
  if (typeof value.tool !== "string" || typeof value.net !== "string") {
    return fail("a proof report needs a tool and a net name");
  }
  if (value.source !== null && typeof value.source !== "string") {
    return fail("proof report source must be a string or null");
  }
  if (!Array.isArray(value.facts)) return fail("proof report facts must be a list");
  if (!isRecord(value.model)) return fail("proof report model must be an object");
  const facts = value.facts.map((item, index) => asFact(item, index));
  return {
    version: REPORT_VERSION,
    tool: value.tool,
    net: value.net,
    source: value.source,
    status: asStatus(value.status, "proof report"),
    facts,
    model: value.model,
    ...(value.exploration === undefined
      ? {}
      : {
          exploration: isRecord(value.exploration)
            ? value.exploration
            : fail("proof report exploration must be an object"),
        }),
    ...(value.composition === undefined
      ? {}
      : {
          composition: isRecord(value.composition)
            ? value.composition
            : fail("proof report composition must be an object"),
        }),
  };
}
