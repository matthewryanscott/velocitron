import type {
  FiringRecord,
  InjectionRecord,
  Marking,
  Net,
  ReadonlyJsonObject,
  Token,
} from "@velocitron/engine";
import type {Play, PlayPath, Step} from "@velocitron/play";

export type OutputRule = "net" | "play" | "merge" | "carry" | "nothing";

export interface OutputSource {
  readonly place: string;
  readonly color: string;
  readonly rule: OutputRule;
}

export interface CheckResult {
  readonly text: string;
  readonly ok: boolean;
  readonly detail: string;
  readonly kind: string;
}

export interface StepDiagnostic {
  readonly code: string;
  readonly message: string;
  readonly line: number;
  readonly column: number;
  readonly details: readonly string[];
}

export interface StepResult {
  readonly step: Step;
  readonly path: string;
  readonly index: number;
  readonly before: Marking;
  readonly after: Marking;
  readonly records: readonly (FiringRecord | InjectionRecord)[];
  readonly markings: readonly Marking[];
  readonly binding: Readonly<Record<string, readonly Token[]>>;
  readonly consumed: Readonly<Record<string, readonly Token[]>>;
  readonly read: Readonly<Record<string, readonly Token[]>>;
  readonly produced: Readonly<Record<string, readonly Token[]>>;
  readonly replaced: Readonly<Record<string, readonly Token[]>>;
  readonly outputs: readonly OutputSource[];
  readonly checks: readonly CheckResult[];
}

export interface StepFailure {
  readonly step: Step;
  readonly path: string;
  readonly index: number;
  readonly before: Marking;
  readonly diagnostic: StepDiagnostic;
  readonly checks: readonly CheckResult[];
  readonly enabled: readonly string[];
}

/** The net a play resolves: one document, or the merge of a composition. */
export interface PlayNet {
  readonly net: Net;
  readonly label: string;
  readonly document: ReadonlyJsonObject | null;
  readonly placeNames: ReadonlyMap<string, string>;
  readonly composed: boolean;
  readonly refined: ReadonlyMap<string, string>;
}

export interface PlayTrace {
  readonly play: Play;
  readonly subject: PlayNet;
  readonly path: PlayPath;
  readonly initial: Marking;
  readonly steps: readonly StepResult[];
  readonly failure: StepFailure | null;
  readonly inherited: number;
  readonly passed: boolean;
  readonly final: Marking;
}

export interface PlayReport {
  readonly play: Play;
  readonly subject: PlayNet;
  readonly traces: readonly PlayTrace[];
  readonly passed: boolean;
  trace(path: string): PlayTrace | null;
  diagnostics(): readonly StepDiagnostic[];
}
