/**
 * Read a Velocitron proof report.
 *
 * `readProofReport` checks the JSON document from `packages/spec/proofs.md`.
 * `proofReportStatus` applies the report's status rule: refuted, then
 * unknown, then proved.
 *
 * The prover itself is Python (`velocitron_analysis.prove`). This package
 * does not explore a net, compile CEL, check kept records, or lint. It
 * does not import `@velocitron/core`.
 */

export {
  FACTS,
  REPORT_VERSION,
  ProofReportError,
  proofReportStatus,
  readProofReport,
} from "./report.js";
export type {
  ProofFact,
  ProofFinding,
  ProofMove,
  ProofReportDocument,
  ProofStatus,
  ProofToken,
  RequestedFact,
  StoredFact,
} from "./report.js";
