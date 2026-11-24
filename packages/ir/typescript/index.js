/**
 * Load a Velocitron contribution-IR document as a wire shape.
 *
 * A checkout reads packages/spec/petrinet-contribution-ir.schema.json. An
 * installed package reads the copy beside this file, which
 * tools/generate-schemas-python.py keeps identical to that schema.
 *
 * Format, version, and the wire schema are checked here. CEL source strings
 * stay strings. Contribution resolution stays in the language
 * implementations. Composition merge ships in `packages/merge`; the
 * implementations keep their own copies.
 */

import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import Ajv2020 from "ajv/dist/2020.js";

export const CONTRIBUTION_IR_FORMAT = "velocitron.petrinet/contribution-ir";
export const CONTRIBUTION_IR_VERSION = 1;
export const CONTRIBUTION_IR_SCHEMA_NAME = "petrinet-contribution-ir.schema.json";

const UNSUPPORTED = "unsupported contribution IR format or version";
const NOT_OBJECT = "contribution IR document must be a JSON object";
const NOT_JSON = "contribution IR text is not JSON";
const SCHEMA_MISMATCH = "contribution IR document does not match the wire schema";
const DOCUMENT_KEYS = Object.freeze([
  "contributions",
  "document",
  "documentKind",
  "format",
  "version",
]);

const here = dirname(fileURLToPath(import.meta.url));

function readSchemaText() {
  const canonical = resolve(here, `../../spec/${CONTRIBUTION_IR_SCHEMA_NAME}`);
  const specProject = resolve(here, "../../spec/pyproject.toml");
  if (existsSync(specProject) && existsSync(canonical)) return readFileSync(canonical, "utf8");
  const packaged = resolve(here, CONTRIBUTION_IR_SCHEMA_NAME);
  if (!existsSync(packaged)) {
    throw new Error("@velocitron/ir contribution IR schema is not installed");
  }
  return readFileSync(packaged, "utf8");
}

const schemaText = readSchemaText();
const schema = JSON.parse(schemaText);
const ajv = new Ajv2020({
  allErrors: true,
  strict: false,
  strictNumbers: true,
  validateFormats: false,
});
const validate = ajv.compile(structuredClone(schema));

export class ContributionIrShapeError extends Error {
  /**
   * @param {string} message
   * @param {readonly ContributionIrShapeIssue[]} [issues]
   */
  constructor(message, issues = []) {
    super(message);
    this.name = "ContributionIrShapeError";
    this.issues = issues;
  }
}

function isJsonObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function issue(instancePath, message) {
  return Object.freeze({
    instancePath,
    message,
  });
}

function schemaIssues(errors) {
  return Object.freeze(
    [...(errors ?? [])]
      .map((error) => issue(error.instancePath ?? "", error.message ?? "invalid"))
      .sort((left, right) => {
        if (left.instancePath < right.instancePath) return -1;
        if (left.instancePath > right.instancePath) return 1;
        if (left.message < right.message) return -1;
        if (left.message > right.message) return 1;
        return 0;
      }),
  );
}

function requireSupportedFormat(document) {
  if (
    document.format !== CONTRIBUTION_IR_FORMAT ||
    document.version !== CONTRIBUTION_IR_VERSION
  ) {
    throw new ContributionIrShapeError(UNSUPPORTED);
  }
}

function sameDocumentKeys(document) {
  const keys = Object.keys(document);
  return (
    keys.length === DOCUMENT_KEYS.length &&
    DOCUMENT_KEYS.every((key) => Object.hasOwn(document, key))
  );
}

/**
 * @param {unknown} document
 * @returns {import("./index.js").ContributionIr}
 */
export function loadContributionIr(document) {
  if (!isJsonObject(document)) throw new ContributionIrShapeError(NOT_OBJECT);
  requireSupportedFormat(document);
  if (!validate(document)) {
    throw new ContributionIrShapeError(SCHEMA_MISMATCH, schemaIssues(validate.errors));
  }
  if (!sameDocumentKeys(document)) throw new ContributionIrShapeError(SCHEMA_MISMATCH);
  return structuredClone(document);
}

/**
 * @param {string} text
 * @returns {import("./index.js").ContributionIr}
 */
export function loadContributionIrText(text) {
  if (typeof text !== "string") {
    throw new TypeError("contribution IR text must be a string");
  }
  let value;
  try {
    value = JSON.parse(text);
  } catch {
    throw new ContributionIrShapeError(NOT_JSON);
  }
  return loadContributionIr(value);
}

export function contributionIrSchemaText() {
  return schemaText;
}

export function contributionIrSchema() {
  return structuredClone(schema);
}
