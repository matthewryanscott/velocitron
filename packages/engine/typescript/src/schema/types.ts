export type JsonPrimitive = null | boolean | number | string;

export type JsonValue =
  | JsonPrimitive
  | readonly JsonValue[]
  | ReadonlyJsonObject;

export interface ReadonlyJsonObject {
  readonly [key: string]: JsonValue;
}

export interface Token {
  readonly type: string;
  readonly data: ReadonlyJsonObject;
}

/** An immutable marking for Engine calls and initial markings. */
export type Marking = Readonly<Record<string, readonly Token[]>>;

export interface Port {
  readonly direction: "input" | "output";
  readonly type: string;
}

export interface CapacityPerColorKey {
  readonly key: string | readonly string[];
  readonly max: number;
}

export interface Place {
  readonly name: string;
  readonly accepts: readonly string[];
  readonly port?: Port;
  readonly capacityPerColorKey?: CapacityPerColorKey;
  readonly description?: string;
  readonly annotations?: ReadonlyJsonObject;
}

export interface Timer {
  readonly clock: string;
  readonly cel: string;
  readonly bind?: Readonly<Record<string, string>>;
  readonly maturity?: string;
}

export interface Transition {
  readonly name: string;
  readonly handler?: string;
  readonly guard?: string;
  readonly priority?: number;
  readonly timer?: Timer;
  readonly description?: string;
  readonly annotations?: ReadonlyJsonObject;
  /** Key -> place: the key CEL's `binding` uses for each binding place (ADR 0032). */
  readonly bindingNames?: Readonly<Record<string, string>>;
}

export type Predicate =
  | Readonly<{cel: string; handler?: never}>
  | Readonly<{handler: string; cel?: never}>;

export interface Correlate {
  readonly cel: string;
}

export interface ConsumePattern {
  readonly type: string;
  readonly mode: "consume" | "inhibit" | "read";
  readonly weight: number;
  readonly predicate?: Predicate;
  readonly correlate?: Correlate;
}

export interface ProduceTemplate {
  readonly type: string;
  readonly destination: string;
  readonly data?: ReadonlyJsonObject;
  readonly cel?: string;
}

export interface PlaceEndpoint {
  readonly place: string;
  readonly transition?: never;
}

export interface TransitionEndpoint {
  readonly transition: string;
  readonly place?: never;
}

export interface ConsumeArc {
  readonly from: PlaceEndpoint;
  readonly to: TransitionEndpoint;
  readonly consume: ConsumePattern;
  readonly produce?: never;
  readonly description?: string;
  readonly annotations?: ReadonlyJsonObject;
}

export interface ProduceArc {
  readonly from: TransitionEndpoint;
  readonly to: PlaceEndpoint;
  readonly produce: ProduceTemplate;
  readonly consume?: never;
  readonly description?: string;
  readonly annotations?: ReadonlyJsonObject;
}

export type Arc = ConsumeArc | ProduceArc;

/** A place invariant the author claims; only `velocitron prove` reads it (ADR 0037). */
export interface DeclaredInvariant {
  readonly weights: Readonly<Record<string, number>>;
  readonly constant?: number;
  readonly name?: string;
}

/**
 * Claims about the net that only `velocitron prove` checks (ADR 0037). Each
 * `final` entry is a final marking: a place, or places that must all hold a
 * token (ADR 0049).
 */
export interface ProofFacts {
  readonly final?: readonly (string | readonly string[])[];
  readonly invariants?: readonly DeclaredInvariant[];
}

export interface Net {
  readonly name: string;
  readonly places: readonly Place[];
  readonly transitions: readonly Transition[];
  readonly arcs: readonly Arc[];
  readonly initialMarking?: Marking;
  readonly description?: string;
  readonly annotations?: ReadonlyJsonObject;
  /** `color.field.path` -> its closed values; the engine rejects tokens outside them (ADR 0037). */
  readonly domains?: Readonly<Record<string, readonly (boolean | number | string)[]>>;
  readonly proofs?: ProofFacts;
}

export interface CompositionNetRef {
  readonly ref: string;
  readonly alias?: string;
}

export interface CompositionPortEndpoint {
  readonly net: string;
  readonly port: string;
}

export interface CompositionWire {
  readonly from: CompositionPortEndpoint;
  readonly to: CompositionPortEndpoint;
}

/** The `by` net replaces the `net` net's `transition` during the merge. */
export interface CompositionRefinement {
  readonly net: string;
  readonly transition: string;
  readonly by: string;
}

/** One member of a share: a place, not necessarily a port, on the net referenced by `net`. */
export interface CompositionPlaceEndpoint {
  readonly net: string;
  readonly place: string;
}

/** Places of several referenced nets that are one place in the merged net, with no direction. */
export interface CompositionShare {
  readonly places: readonly CompositionPlaceEndpoint[];
}

/** Shape-only composition document. References are deliberately unresolved. */
export interface CompositionDocument {
  readonly name?: string;
  readonly nets: readonly CompositionNetRef[];
  readonly wires: readonly CompositionWire[];
  readonly shares?: readonly CompositionShare[];
  readonly refinements?: readonly CompositionRefinement[];
  /** Final markings of the merged net, replacing its nets' final places (ADR 0049). */
  readonly final?: readonly (readonly CompositionPlaceEndpoint[])[];
}
