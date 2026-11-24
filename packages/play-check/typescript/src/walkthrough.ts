import type {Marking, Token} from "@velocitron/engine";

import type {CheckResult, PlayTrace, StepFailure, StepResult} from "./model.js";

export type WalkScope = "step" | "neighbors" | "subnet";

export interface MarkingJson {
  readonly [place: string]: readonly {readonly type: string; readonly data: Token["data"]}[];
}

export interface WalkthroughStep {
  readonly number: number | null;
  readonly heading: string;
  readonly statement: string;
  readonly line: number;
  readonly status: string;
  readonly prose: string;
  readonly checks: readonly CheckResult[];
  readonly before: MarkingJson | null;
  readonly after: MarkingJson | null;
}

export interface WalkthroughDocument {
  readonly play: string;
  readonly title: string;
  readonly path: string;
  readonly pathTitle: string | null;
  readonly net: string;
  readonly status: "passed" | "failed";
  readonly scope: string;
  readonly prose: string;
  readonly steps: readonly WalkthroughStep[];
  readonly failure: {
    readonly code: string;
    readonly message: string;
    readonly line: number;
    readonly column: number;
    readonly details: readonly string[];
  } | null;
}

/** One marking as JSON. Places with no tokens are omitted. */
export function markingJson(marking: Marking): MarkingJson {
  const document: Record<string, {type: string; data: Token["data"]}[]> = {};
  for (const [place, tokens] of Object.entries(marking)) {
    if (tokens.length === 0) continue;
    document[place] = tokens.map((token) => ({type: token.type, data: token.data}));
  }
  return document;
}

function heading(number: number, statement: string): string {
  return `${number}. ${statement}`;
}

function stepDocument(
  number: number | null,
  result: StepResult,
  status: string,
): WalkthroughStep {
  const changes = result.step.kind !== "expect" && result.step.kind !== "assume";
  return {
    number,
    heading: number === null ? result.step.statement : heading(number, result.step.statement),
    statement: result.step.statement,
    line: result.step.position.line,
    status,
    prose: result.step.prose,
    checks: result.checks,
    before: changes ? markingJson(result.before) : null,
    after: changes ? markingJson(result.after) : null,
  };
}

function failureDocument(number: number, failure: StepFailure): WalkthroughStep {
  return {
    number,
    heading: heading(number, failure.step.statement),
    statement: failure.step.statement,
    line: failure.step.position.line,
    status: "failed",
    prose: failure.step.prose,
    checks: failure.checks,
    before: markingJson(failure.before),
    after: null,
  };
}

/**
 * Step a checked path as a walkthrough document.
 *
 * Each marking-changing step carries the marking before and after it.
 * Paired Graphviz graphs and PlantUML stay in the Python package: this
 * runtime has no `netTwinDots` and does not draw a sequence diagram.
 */
export function walkthroughDocument(
  trace: PlayTrace,
  options: {readonly scope?: WalkScope} = {},
): WalkthroughDocument {
  const scope = options.scope ?? trace.play.scope ?? "step";
  const steps: WalkthroughStep[] = [];
  let number = 0;
  for (const result of trace.steps) {
    if (result.step.kind === "expect") {
      const previous = steps[steps.length - 1];
      if (previous !== undefined) {
        steps[steps.length - 1] = {
          ...previous,
          checks: [...previous.checks, ...result.checks],
          prose: [previous.prose, result.step.prose].filter((part) => part.length > 0).join("\n\n"),
        };
      }
      continue;
    }
    number += 1;
    steps.push(stepDocument(number, result, "completed"));
  }
  if (trace.failure !== null && trace.failure.step.kind !== "expect") {
    number += 1;
    steps.push(failureDocument(number, trace.failure));
  } else if (trace.failure?.step.kind === "expect") {
    const previous = steps[steps.length - 1];
    if (previous !== undefined) {
      steps[steps.length - 1] = {
        ...previous,
        status: "failed",
        checks: [...previous.checks, ...trace.failure.checks],
      };
    }
  }
  return {
    play: trace.play.name,
    title: trace.play.title ?? trace.play.name,
    path: trace.path.name,
    pathTitle: trace.path.title,
    net: trace.subject.label,
    status: trace.passed ? "passed" : "failed",
    scope,
    prose: [trace.play.prose, trace.path.prose].filter((part) => part.length > 0).join("\n\n"),
    steps,
    failure: trace.failure === null
      ? null
      : {
          code: trace.failure.diagnostic.code,
          message: trace.failure.diagnostic.message,
          line: trace.failure.diagnostic.line,
          column: trace.failure.diagnostic.column,
          details: trace.failure.diagnostic.details,
        },
  };
}

/** One path as JSON: statements, records, markings, and checks. */
export function traceJson(trace: PlayTrace): {
  readonly play: string;
  readonly path: string;
  readonly passed: boolean;
  readonly initial: MarkingJson;
  readonly steps: readonly {
    readonly statement: string;
    readonly checks: readonly CheckResult[];
    readonly before: MarkingJson;
    readonly after: MarkingJson;
    readonly records: readonly unknown[];
  }[];
  readonly failure: WalkthroughDocument["failure"];
} {
  const document = walkthroughDocument(trace);
  return {
    play: trace.play.name,
    path: trace.path.name,
    passed: trace.passed,
    initial: markingJson(trace.initial),
    steps: trace.steps.map((result) => ({
      statement: result.step.statement,
      checks: result.checks,
      before: markingJson(result.before),
      after: markingJson(result.after),
      records: result.records,
    })),
    failure: document.failure,
  };
}

/** Markdown for one checked path. It names each statement and does not embed DOT. */
export function renderWalkthrough(trace: PlayTrace): string {
  const document = walkthroughDocument(trace);
  const lines = [`# ${document.title}`, "", `Path \`${document.path}\` against ${document.net}.`, ""];
  if (document.prose.length > 0) lines.push(document.prose, "");
  for (const step of document.steps) {
    lines.push(`## ${step.heading}`, "");
    if (step.prose.length > 0) lines.push(step.prose, "");
    if (step.before !== null) {
      lines.push("Before:", "", "```json", JSON.stringify(step.before), "```", "");
    }
    if (step.after !== null) {
      lines.push("After:", "", "```json", JSON.stringify(step.after), "```", "");
    }
    for (const check of step.checks) {
      lines.push(`- ${check.ok ? "ok" : "fail"} \`${check.text}\`${check.detail.length > 0 ? ` — ${check.detail}` : ""}`);
    }
    if (step.checks.length > 0) lines.push("");
  }
  if (document.failure !== null) {
    lines.push(
      `Failed ${document.failure.code}: ${document.failure.message}`,
      "",
    );
  }
  return lines.join("\n");
}
