import {deepFreezeJson} from "./json.js";
import type {ReadonlyJsonObject} from "./types.js";

export type NetValidationIssueCode =
  | "json.array_property"
  | "json.cycle"
  | "json.invalid_property"
  | "json.max_container_entries"
  | "json.max_depth"
  | "json.max_total_values"
  | "json.non_finite_number"
  | "json.non_plain_array"
  | "json.non_plain_object"
  | "json.sparse_array"
  | "json.symbol_key"
  | "json.unreadable_object"
  | "json.unsafe_number"
  | "json.unsupported_type"
  | "schema.invalid"
  | "place.duplicate_name"
  | "transition.duplicate_name"
  | "transition.binding_names.sources_mismatch"
  | "port.type_not_accepted"
  | "arc.consume.direction"
  | "arc.produce.direction"
  | "arc.place_undeclared"
  | "arc.transition_undeclared"
  | "arc.consume.type_not_accepted"
  | "arc.consume.weight_invalid"
  | "arc.inhibit.weight_not_allowed"
  | "arc.predicate.cel_invalid"
  | "arc.correlate.cel_invalid"
  | "arc.produce.destination_mismatch"
  | "arc.produce.type_not_accepted"
  | "arc.produce.cel_data_exclusive"
  | "arc.produce.cel_invalid"
  | "timer.clock_undeclared"
  | "timer.bind.clock_reserved"
  | "timer.bind.source_invalid"
  | "timer.cel_invalid"
  | "timer.maturity.cel_invalid"
  | "domain.color_unknown"
  | "proofs.place_undeclared"
  | "composition.domain_conflict"
  | "composition.actor_conflict"
  | "composition.loader_missing"
  | "composition.loader_failed"
  | "composition.ref_invalid"
  | "composition.alias_derived_invalid"
  | "composition.duplicate_alias"
  | "composition.alias_unknown"
  | "composition.port_undeclared"
  | "composition.port_direction"
  | "composition.wire.type_mismatch"
  | "composition.reference_cycle"
  | "composition.share.alias_unknown"
  | "composition.share.place_unknown"
  | "composition.share.colors"
  | "composition.share.duplicate_member"
  | "composition.final.alias_unknown"
  | "composition.final.place_unknown"
  | "composition.final.duplicate_member"
  | "composition.refinement.by_composition"
  | "composition.refinement.alias_unknown"
  | "composition.refinement.self"
  | "composition.refinement.duplicate"
  | "composition.refinement.transition_unknown"
  | "composition.refinement.unsupported"
  | "composition.refinement.unfit";

export interface NetValidationIssue {
  readonly code: NetValidationIssueCode;
  /** RFC 6901 JSON Pointer into the submitted document. */
  readonly path: string;
  readonly message: string;
  readonly details?: ReadonlyJsonObject;
}

export class NetValidationError extends Error {
  readonly issues: readonly NetValidationIssue[];

  constructor(issues: readonly NetValidationIssue[]) {
    if (issues.length === 0) throw new TypeError("NetValidationError requires an issue");
    const first = issues[0];
    if (first === undefined) throw new TypeError("NetValidationError requires an issue");
    super(
      issues.length === 1
        ? first.message
        : `Net validation failed with ${issues.length} issues; first: ${first.message}`,
    );
    this.name = "NetValidationError";
    this.issues = Object.freeze(
      issues.map((issue) => {
        const details = issue.details === undefined
          ? undefined
          : deepFreezeJson(issue.details);
        return Object.freeze({...issue, ...(details === undefined ? {} : {details})});
      }),
    );
  }
}
