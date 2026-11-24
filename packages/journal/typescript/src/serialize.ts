import type {Token} from "@velocitron/engine";

function isToken(value: object): value is Token {
  if (!("type" in value) || !("data" in value)) return false;
  const token = value as {type: unknown; data: unknown};
  return typeof token.type === "string" && token.data !== null && typeof token.data === "object" && !Array.isArray(token.data);
}

/**
 * Record-payload serializer shared by the file and sqlite journals.
 *
 * A class instance shaped like a token becomes ``{type, data}``. Any other
 * class instance throws. Plain JSON values pass through.
 */
export function serializeRecordValue(value: unknown): unknown {
  if (value === null || typeof value !== "object") {
    if (typeof value === "bigint" || typeof value === "function" || typeof value === "symbol" || value === undefined) {
      throw new TypeError(`cannot serialize ${typeof value} into a record payload`);
    }
    return value;
  }
  if (Array.isArray(value)) return value;
  const prototype: unknown = Object.getPrototypeOf(value);
  if (prototype === Object.prototype || prototype === null) return value;
  if (isToken(value)) return {type: value.type, data: value.data};
  const name = value.constructor?.name ?? "object";
  throw new TypeError(`cannot serialize ${name} into a record payload`);
}

/** ``JSON.stringify`` replacer that fails on a class instance the journal cannot replay. */
export function recordReplacer(_key: string, value: unknown): unknown {
  if (value !== null && typeof value === "object") {
    const prototype: unknown = Object.getPrototypeOf(value);
    if (prototype !== Object.prototype && prototype !== Array.prototype && prototype !== null) {
      return serializeRecordValue(value);
    }
  }
  return value;
}

export function stringifyRecord(record: unknown): string {
  return JSON.stringify(record, recordReplacer);
}
