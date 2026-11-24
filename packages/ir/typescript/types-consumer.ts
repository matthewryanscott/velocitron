import {
  CONTRIBUTION_IR_FORMAT,
  CONTRIBUTION_IR_VERSION,
  contributionIrSchemaText,
  loadContributionIr,
  loadContributionIrText,
  type ContributionIr,
} from "./index.js";

export function readKind(document: ContributionIr): ContributionIr["documentKind"] {
  const loaded = loadContributionIr(document);
  const schema = contributionIrSchemaText();
  return loaded.format === CONTRIBUTION_IR_FORMAT &&
    loaded.version === CONTRIBUTION_IR_VERSION &&
    schema.length > 0
    ? loaded.documentKind
    : loadContributionIrText("{}").documentKind;
}
