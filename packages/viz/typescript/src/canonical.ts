/**
 * RFC 8785 JSON for token labels.
 *
 * This is a port of the primitive renderer in `velocitron.dsl.api`. Object
 * members sort by UTF-16 code units. It does not compile CEL or load
 * documents.
 */

import type {JsonValue, ReadonlyJsonObject} from "./schema/types.js";

const SAFE_INTEGER = 9_007_199_254_740_991;

function jsonString(value: string): string {
  return JSON.stringify(value);
}

function binary64(value: number): string {
  if (!Number.isFinite(value)) throw new Error("JSON numbers must be finite");
  if (Object.is(value, 0) || Object.is(value, -0)) return "0";
  const negative = value < 0;
  const rendered = String(negative ? -value : value).toLowerCase();
  const [coefficient = "", rawExponent] = splitExponent(rendered);
  const [integer = "", fraction = ""] = coefficient.split(".");
  const significand = (integer + fraction).replace(/^0+/, "");
  let exponent = (rawExponent === undefined ? 0 : Number(rawExponent)) - fraction.length;
  const digits = significand.replace(/0+$/, "");
  exponent += significand.length - digits.length;
  const adjusted = exponent + digits.length - 1;
  let magnitude: string;
  if (adjusted >= -6 && adjusted < 21) {
    const decimalAt = digits.length + exponent;
    if (decimalAt <= 0) magnitude = `0.${"0".repeat(-decimalAt)}${digits}`;
    else if (decimalAt >= digits.length) {
      magnitude = digits + "0".repeat(decimalAt - digits.length);
    } else magnitude = `${digits.slice(0, decimalAt)}.${digits.slice(decimalAt)}`;
  } else {
    magnitude = digits[0] ?? "0";
    if (digits.length > 1) magnitude += `.${digits.slice(1)}`;
    magnitude += `e${adjusted}`;
  }
  return (negative ? "-" : "") + magnitude;
}

function splitExponent(rendered: string): [string, string | undefined] {
  const index = rendered.indexOf("e");
  if (index === -1) return [rendered, undefined];
  return [rendered.slice(0, index), rendered.slice(index + 1)];
}

export function renderCanonicalJson(value: JsonValue): string {
  const render = (item: JsonValue): string => {
    if (item === null) return "null";
    if (item === true) return "true";
    if (item === false) return "false";
    if (typeof item === "number") {
      if (!Number.isInteger(item)) return binary64(item);
      if (Math.abs(item) > SAFE_INTEGER) {
        throw new Error("JSON integer exceeds the safe IEEE-754 range");
      }
      return String(item);
    }
    if (typeof item === "string") return jsonString(item);
    if (Array.isArray(item)) {
      if (item.length === 0) return "[]";
      return `[${item.map((child) => render(child)).join(",")}]`;
    }
    if (!isJsonObject(item)) {
      throw new Error("JSON value is not an object");
    }
    const keys = Object.keys(item).sort((left, right) => {
      const a = utf16(left);
      const b = utf16(right);
      const count = Math.min(a.length, b.length);
      for (let index = 0; index < count; index += 1) {
        const delta = a[index]! - b[index]!;
        if (delta !== 0) return delta;
      }
      return a.length - b.length;
    });
    if (keys.length === 0) return "{}";
    return `{${keys
      .map((key) => `${jsonString(key)}:${render(item[key]!)}`)
      .join(",")}}`;
  };
  return render(value);
}

function isJsonObject(value: JsonValue): value is ReadonlyJsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function utf16(value: string): number[] {
  const units: number[] = [];
  for (let index = 0; index < value.length; index += 1) units.push(value.charCodeAt(index));
  return units;
}
