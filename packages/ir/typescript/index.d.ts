export const CONTRIBUTION_IR_FORMAT: "velocitron.petrinet/contribution-ir";
export const CONTRIBUTION_IR_VERSION: 1;
export const CONTRIBUTION_IR_SCHEMA_NAME: "petrinet-contribution-ir.schema.json";

export interface ContributionIrPosition {
  readonly byteOffset: number;
  readonly line: number;
  readonly column: number;
}

export interface ContributionIrSpan {
  readonly source: string;
  readonly start: ContributionIrPosition;
  readonly end: ContributionIrPosition;
}

export interface ContributionIrIdentity {
  readonly source: string;
  readonly statement: number;
  readonly part: number;
}

export interface ContributionIrDocument {
  readonly id: string;
}

export interface ContributionIrContribution {
  readonly id: ContributionIrIdentity;
  readonly ordinal: number;
  readonly span: ContributionIrSpan;
  readonly kind: string;
  readonly target: Readonly<Record<string, ContributionIrJson>>;
  readonly value: Readonly<Record<string, ContributionIrJson>>;
}

export type ContributionIrJson =
  | null
  | boolean
  | number
  | string
  | readonly ContributionIrJson[]
  | { readonly [key: string]: ContributionIrJson };

export interface ContributionIr {
  readonly format: "velocitron.petrinet/contribution-ir";
  readonly version: 1;
  readonly documentKind: "net" | "composition";
  readonly document: ContributionIrDocument;
  readonly contributions: readonly ContributionIrContribution[];
}

export interface ContributionIrShapeIssue {
  readonly instancePath: string;
  readonly message: string;
}

export class ContributionIrShapeError extends Error {
  readonly issues: readonly ContributionIrShapeIssue[];
  constructor(message: string, issues?: readonly ContributionIrShapeIssue[]);
}

export function loadContributionIr(document: unknown): ContributionIr;
export function loadContributionIrText(text: string): ContributionIr;
export function contributionIrSchemaText(): string;
export function contributionIrSchema(): ContributionIrJson;
