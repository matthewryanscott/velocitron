/**
 * The single owner of the Python-repr dialect used in diagnostics. CPython's
 * `repr()` (via `{value!r}` inside the Python compiler and resolver) is the
 * oracle for every byte these helpers emit, so cross-language corpus
 * diagnostic expectations stay byte-identical.
 */

/**
 * A closed lossless representation of an RFC 8259 JSON value. Objects use
 * ordered entries so object-entry order and number lexemes survive
 * target-neutral reconstruction (the same wire the generated IR schema pins).
 */
export type TaggedJsonValue =
  | { type: "null" }
  | { type: "boolean"; value: boolean }
  | { type: "string"; value: string }
  | { type: "number"; lexeme: string }
  | { type: "array"; items: TaggedJsonValue[] }
  | {
      type: "object";
      entries: Array<{ key: string; value: TaggedJsonValue }>;
    };

/**
 * CPython treats a character as non-printable exactly when it belongs to Cc,
 * Cf, Cs, Co, Cn, Zl, Zp, or Zs other than U+0020 — the JS `\\p{C}\\p{Z}`
 * set with the plain space carved out.
 */
const PYTHON_NON_PRINTABLE = /[\p{C}\p{Z}]/u;

/** Render one string exactly as CPython `repr` renders a `str`. */
export function pythonStringRepr(value: string): string {
  const quote = value.includes("'") && !value.includes('"') ? '"' : "'";
  let rendered = quote;
  for (const character of value) {
    const escaped =
      character === "\\"
        ? "\\\\"
        : character === quote
          ? `\\${character}`
          : character === "\n"
            ? "\\n"
            : character === "\r"
              ? "\\r"
              : character === "\t"
                ? "\\t"
                : undefined;
    if (escaped !== undefined) {
      rendered += escaped;
      continue;
    }
    // CPython special-cases only \n, \r, and \t; every other control
    // character (including \x07, \x0b, \x0c, and \x7f) renders as a hex escape.
    if (character !== " " && PYTHON_NON_PRINTABLE.test(character)) {
      const codePoint = character.codePointAt(0) as number;
      rendered += codePoint <= 0xff
        ? `\\x${codePoint.toString(16).padStart(2, "0")}`
        : codePoint <= 0xffff
          ? `\\u${codePoint.toString(16).padStart(4, "0")}`
          : `\\U${codePoint.toString(16).padStart(8, "0")}`;
      continue;
    }
    rendered += character;
  }
  return `${rendered}${quote}`;
}

/**
 * Render a finite binary64 value exactly as CPython `repr` (the shortest
 * round-tripping decimal, rendered in scientific form when the decimal
 * exponent is < -4 or >= 16, with a two-digit signed exponent and `.0`
 * appended to integral exponents inside that window).
 */
export function reprFloat(value: number): string {
  if (Object.is(value, -0)) return "-0.0";

  const rendered = String(value);
  const scientific = rendered.match(/^(-?)(\d(?:\.\d+)?)e([+-]?)(\d+)$/u);
  if (scientific !== null) {
    const [, sign, mantissa, exponentSign, exponentDigits] = scientific;
    const normalizedSign = exponentSign === "-" ? "-" : "+";
    return `${sign}${mantissa}e${normalizedSign}${exponentDigits.padStart(2, "0")}`;
  }

  const negative = rendered.startsWith("-");
  const magnitude = negative ? rendered.slice(1) : rendered;
  const [integer, fraction = ""] = magnitude.split(".");
  const firstFractionDigit = fraction.search(/[1-9]/u);
  const exponent = integer === "0"
    ? -(firstFractionDigit + 1)
    : integer.length - 1;
  if (exponent < -4 || exponent >= 16) {
    const digits = `${integer}${fraction}`.replace(/^0+/u, "").replace(/0+$/u, "");
    const mantissa = digits.length === 1 ? digits : `${digits[0]}.${digits.slice(1)}`;
    const exponentSign = exponent < 0 ? "-" : "+";
    return `${negative ? "-" : ""}${mantissa}e${exponentSign}${Math.abs(exponent).toString().padStart(2, "0")}`;
  }
  return Number.isInteger(value) ? `${rendered}.0` : rendered;
}

/**
 * Render an already-parsed JavaScript value exactly as CPython `repr`
 * renders the JSON-parsed Python value (`None`, `True`, `False`, `int`,
 * `float`, `str`, `list`, `dict`). Integral numbers render as Python
 * integers because `json.loads` produces `int` for integer literals.
 */
export function pythonRepr(value: unknown): string {
  if (value === null) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "string") return pythonStringRepr(value);
  if (typeof value === "number") {
    if (Number.isInteger(value)) return String(value);
    return reprFloat(value);
  }
  if (Array.isArray(value)) return `[${value.map(pythonRepr).join(", ")}]`;
  if (typeof value === "object" && value !== null) {
    return `{${Object.entries(value)
      .map(([key, item]) => `${pythonRepr(key)}: ${pythonRepr(item)}`)
      .join(", ")}}`;
  }
  return String(value);
}

/** Render a tagged JSON number lexeme exactly as CPython `repr` renders the value `json.loads` produces for it. */
export function taggedNumberRepr(lexeme: string): string {
  const value = Number(lexeme);
  if (!lexeme.includes(".") && !lexeme.includes("e") && !lexeme.includes("E")) {
    return String(value);
  }
  return reprFloat(value);
}

/** Render a tagged JSON value exactly as CPython `repr` renders the parsed contribution value. */
export function taggedPythonRepr(value: TaggedJsonValue): string {
  switch (value.type) {
    case "null":
      return "None";
    case "boolean":
      return value.value ? "True" : "False";
    case "string":
      return pythonStringRepr(value.value);
    case "number":
      return taggedNumberRepr(value.lexeme);
    case "array":
      return `[${value.items.map(taggedPythonRepr).join(", ")}]`;
    case "object":
      return `{${value.entries
        .map(
          (entry) =>
            `${pythonStringRepr(entry.key)}: ${taggedPythonRepr(entry.value)}`,
        )
        .join(", ")}}`;
  }
}