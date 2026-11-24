import {
  FACTS,
  readProofReport,
  proofReportStatus,
  type ProofReportDocument,
  type RequestedFact,
} from "./dist/index.js";

export function requested(): readonly RequestedFact[] {
  return FACTS;
}

export function open(value: unknown): ProofReportDocument {
  return readProofReport(value);
}

export function rollup(report: ProofReportDocument): ReturnType<typeof proofReportStatus> {
  return proofReportStatus(report.facts);
}
