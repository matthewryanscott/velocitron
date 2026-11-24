// The Python `repr` dialect is pinned against real CPython behavior: these
// expectations were produced by CPython 3.12 (`repr(value)` / `{value!r}`)
// and keep TS diagnostics byte-identical with the Python corpus oracle.
import {describe, expect, it} from "vitest";
import {
  pythonRepr,
  pythonStringRepr,
  reprFloat,
  taggedNumberRepr,
  taggedPythonRepr,
} from "@velocitron/dsl";

const STRING_CASES: readonly (readonly [string, string])[] = [
  // Control characters: only \t, \n, \r get named escapes in CPython.
  ["\x00", `'\\x00'`],
  ["\x07", `'\\x07'`],
  ["\x08", `'\\x08'`],
  ["\x0b", `'\\x0b'`],
  ["\x0c", `'\\x0c'`],
  ["\t", `'\\t'`],
  ["\n", `'\\n'`],
  ["\r", `'\\r'`],
  ["\r\n", `'\\r\\n'`],
  ["\x1f", `'\\x1f'`],
  ["\x7f", `'\\x7f'`],
  // Quotes and backslashes.
  ["\\", `'\\\\'`],
  [`a"b`, `'a"b'`],
  ["a'b", `"a'b"`],
  [`it's "both"`, `'it\\\'s "both"'`],
  [`"`, `'"'`],
  [`a\\b"c`, `'a\\\\b"c'`],
  // Non-printable Unicode code points render as hex/unicode escapes.
  ["\x85", `'\\x85'`],
  ["\xad", `'\\xad'`],
  ["\u200b", `'\\u200b'`],
  ["\xa0", `'\\xa0'`],
  ["\x9f", `'\\x9f'`],
  ["\u{2ffff}", `'\\U0002ffff'`],
  // Printable Unicode code points pass through untouched.
  ["😀", `'😀'`],
  ["é", `'é'`],
  ["雪", `'雪'`],
  ["text", `'text'`],
];

const FLOAT_CASES: readonly (readonly [number, string])[] = [
  [-0, "-0.0"],
  [1, "1.0"],
  [1.5, "1.5"],
  [1e15, "1000000000000000.0"],
  [1e16, "1e+16"],
  [2 ** 53, "9007199254740992.0"],
  [0.0001, "0.0001"],
  [1e-5, "1e-05"],
  [1e-7, "1e-07"],
  [3.14159265358979, "3.14159265358979"],
  [1e21, "1e+21"],
  [-1.5e300, "-1.5e+300"],
  [123.456, "123.456"],
  [10, "10.0"],
];

describe("Python repr dialect (CPython oracle)", () => {
  it.each(STRING_CASES)("string repr matches CPython for %s", (value, expected) => {
    expect(pythonStringRepr(value)).toBe(expected);
  });

  it.each(FLOAT_CASES)("float repr matches CPython for %o", (value, expected) => {
    expect(reprFloat(value)).toBe(expected);
  });

  it("renders scalars and containers exactly as CPython repr", () => {
    expect(pythonRepr(null)).toBe("None");
    expect(pythonRepr(true)).toBe("True");
    expect(pythonRepr(false)).toBe("False");
    expect(pythonRepr(0)).toBe("0");
    expect(pythonRepr(1.5)).toBe("1.5");
    expect(pythonRepr("a'b")).toBe(`"a'b"`);
    // JSON-written integers parse to integral JS numbers and render as Python
    // int repr (1.0 and 1 are the same value here; the lower path sees the lexeme).
    expect(pythonRepr([null, true, 1.0])).toBe("[None, True, 1]");
    expect(pythonRepr({a: [null, true, 1.0]})).toBe(`{'a': [None, True, 1]}`);
  });

  it("renders tagged numbers by lexeme exactly as CPython repr of the JSON-parsed value", () => {
    expect(taggedNumberRepr("1")).toBe("1");
    expect(taggedNumberRepr("-3")).toBe("-3");
    expect(taggedNumberRepr("1.0")).toBe("1.0");
    expect(taggedNumberRepr("-0.0")).toBe("-0.0");
    expect(taggedNumberRepr("1e-5")).toBe("1e-05");
    expect(taggedNumberRepr("1e30")).toBe("1e+30");
    expect(taggedNumberRepr("1.5e16")).toBe("1.5e+16");
  });

  it("renders tagged structures exactly as CPython repr of the parsed value", () => {
    const tagged: Parameters<typeof taggedPythonRepr>[0] = {
      type: "object",
      entries: [
        {key: "k", value: {type: "array", items: [{type: "null"}, {type: "boolean", value: true}, {type: "number", lexeme: "1.0"}]}},
        {key: "q'te", value: {type: "string", value: "\x07"}},
      ],
    };
    expect(taggedPythonRepr(tagged)).toBe(`{'k': [None, True, 1.0], "q'te": '\\x07'}`);
  });
});