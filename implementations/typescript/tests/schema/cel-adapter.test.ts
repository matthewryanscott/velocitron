import {describe, expect, it} from "vitest";
import {
  CelCompileError,
  CelEvaluationError,
  DefaultCelAdapter,
} from "@velocitron/cel";

describe("DefaultCelAdapter", () => {
  it("compiles once by exact source and evaluates synchronously with dynamic JSON variables", () => {
    const adapter = new DefaultCelAdapter();
    const first = adapter.compile("n >= 1");
    const second = adapter.compile("n >= 1");

    expect(second).toBe(first);
    expect(adapter.evaluate(first, {n: 1})).toBe(true);
    expect(adapter.evaluate(first, {n: 0})).toBe(false);
    expect(typeof first).toBe("object");
    expect(Reflect.ownKeys(first as object)).toEqual([]);
  });

  it("promotes safe JSON integers for portable CEL arithmetic", () => {
    const adapter = new DefaultCelAdapter();
    const missing = adapter.compile("missing.field");
    expect(() => adapter.evaluate(missing, {})).toThrow(CelEvaluationError);

    const arithmetic = adapter.compile("n + 1");
    expect(adapter.evaluate(arithmetic, {n: 1})).toBe(2);
    expect(
      adapter.evaluate(
        adapter.compile("clock.now >= latch.fired_at + latch.cadence_s"),
        {
          clock: {now: 300},
          latch: {cadence_s: 300, fired_at: 0},
        },
      ),
    ).toBe(true);
  });

  it("normalizes compile errors without exposing backend instances", () => {
    const adapter = new DefaultCelAdapter();
    const error = (() => {
      try {
        adapter.compile("value.(");
      } catch (caught) {
        return caught;
      }
      throw new Error("expected CEL compile failure");
    })();

    expect(error).toBeInstanceOf(CelCompileError);
    const normalized = error as CelCompileError;
    expect(normalized.diagnostic.phase).toBe("compile");
    expect(normalized.diagnostic.code).toBeTypeOf("string");
    expect(normalized.diagnostic.summary.length).toBeGreaterThan(0);
    expect("cause" in normalized).toBe(false);
    expect(Object.isFrozen(normalized.diagnostic)).toBe(true);
  });

  it("rejects non-JSON contexts and programs from another adapter", () => {
    const first = new DefaultCelAdapter();
    const second = new DefaultCelAdapter();
    const program = first.compile("value");

    expect(() => first.evaluate(program, {value: new Date() as never})).toThrowError(
      expect.objectContaining({diagnostic: expect.objectContaining({code: "invalid_context"})}),
    );
    expect(() => second.evaluate(program, {value: true})).toThrowError(
      expect.objectContaining({diagnostic: expect.objectContaining({code: "invalid_program"})}),
    );
  });

  it("accepts map and list literals that mix binding values with literals", () => {
    // given: a map and a list that mix literals with a bound value
    const adapter = new DefaultCelAdapter();
    const map = adapter.compile("{'kind': 'held', 'delivery': binding.pending[0].id, 'attempt': 1}");
    const list = adapter.compile("[1, 'a', binding.pending[0].id]");
    const context = {binding: {pending: [{id: "d-1"}]}};

    // when: evaluating both
    const mapResult = adapter.evaluate(map, context);
    const listResult = adapter.evaluate(list, context);

    // then: both evaluate as they do in Python
    expect(mapResult).toEqual({kind: "held", delivery: "d-1", attempt: 1});
    expect(listResult).toEqual([1, "a", "d-1"]);
  });
});
