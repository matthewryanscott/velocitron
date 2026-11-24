import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  CelCompileError,
  CelEvaluationError,
  createDefaultCelAdapter,
} from "../dist/index.js";

describe("DefaultCelAdapter", () => {
  it("compiles once by exact source and evaluates synchronously", () => {
    // given: one adapter and one predicate
    const adapter = createDefaultCelAdapter();
    // when: the same source is compiled twice and evaluated
    const first = adapter.compile("n >= 1");
    const second = adapter.compile("n >= 1");
    const enabled = adapter.evaluate(first, {n: 1});
    const disabled = adapter.evaluate(first, {n: 0});
    // then: the program object is reused and the predicate sees JSON numbers
    assert.equal(second, first);
    assert.equal(enabled, true);
    assert.equal(disabled, false);
    assert.equal(typeof first, "object");
    assert.deepEqual(Reflect.ownKeys(first), []);
  });

  it("promotes safe JSON integers for portable CEL arithmetic", () => {
    // given: a missing field and integer arithmetic over nested JSON
    const adapter = createDefaultCelAdapter();
    const missing = adapter.compile("missing.field");
    const arithmetic = adapter.compile("n + 1");
    const cadence = adapter.compile("clock.now >= latch.fired_at + latch.cadence_s");
    // when: each program is evaluated
    // then: a missing field fails, and safe integers cross back as JSON numbers
    assert.throws(() => adapter.evaluate(missing, {}), CelEvaluationError);
    assert.equal(adapter.evaluate(arithmetic, {n: 1}), 2);
    assert.equal(
      adapter.evaluate(cadence, {
        clock: {now: 300},
        latch: {cadence_s: 300, fired_at: 0},
      }),
      true,
    );
  });

  it("normalizes compile errors without exposing backend instances", () => {
    // given: a source that is not CEL
    const adapter = createDefaultCelAdapter();
    // when: it is compiled
    // then: the failure is a frozen compile diagnostic
    assert.throws(
      () => adapter.compile("value.("),
      (error) => {
        assert.ok(error instanceof CelCompileError);
        assert.equal(error.diagnostic.phase, "compile");
        assert.equal(typeof error.diagnostic.code, "string");
        assert.ok(error.diagnostic.summary.length > 0);
        assert.equal("cause" in error, false);
        assert.equal(Object.isFrozen(error.diagnostic), true);
        return true;
      },
    );
  });

  it("rejects non-JSON contexts and programs from another adapter", () => {
    // given: two adapters and a program from the first
    const first = createDefaultCelAdapter();
    const second = createDefaultCelAdapter();
    const program = first.compile("value");
    // when: the context is not JSON, and the other adapter is given the program
    // then: both failures name the boundary they crossed
    assert.throws(
      () => first.evaluate(program, {value: new Date()}),
      (error) => error instanceof CelEvaluationError && error.diagnostic.code === "invalid_context",
    );
    assert.throws(
      () => second.evaluate(program, {value: true}),
      (error) => error instanceof CelEvaluationError && error.diagnostic.code === "invalid_program",
    );
  });

  it("accepts map and list literals that mix binding values with literals", () => {
    // given: a map and a list that mix literals with a bound value
    const adapter = createDefaultCelAdapter();
    const mapped = adapter.compile("{'kind': 'held', 'delivery': binding.pending[0].id, 'attempt': 1}");
    const listed = adapter.compile("[1, 'a', binding.pending[0].id]");
    const context = {binding: {pending: [{id: "d-1"}]}};
    // when: both are evaluated
    const mapResult = adapter.evaluate(mapped, context);
    const listResult = adapter.evaluate(listed, context);
    // then: both match the Python adapter's values. Map results use a null prototype.
    assert.deepEqual({...mapResult}, {kind: "held", delivery: "d-1", attempt: 1});
    assert.equal(Object.getPrototypeOf(mapResult), null);
    assert.deepEqual(listResult, [1, "a", "d-1"]);
  });

  it("normalizes nested safe integers and rejects non-JSON results", () => {
    // given: nested integers, a fractional number, and results outside JSON
    const adapter = createDefaultCelAdapter();
    const nested = adapter.compile("outer.values[0] + outer.values[1].amount + 1");
    const fraction = adapter.compile("n + 0.25");
    const rows = adapter.compile("[[n + 1], [n + 2], [n + 3]]");
    const unsafe = adapter.compile("9007199254740992");
    const bytes = adapter.compile("b'abc'");
    // when: each is evaluated
    const sum = adapter.evaluate(nested, {outer: {values: [2, {amount: 3}]}});
    const decimal = adapter.evaluate(fraction, {n: 1.5});
    const table = adapter.evaluate(rows, {n: 4});
    // then: safe integers stay JSON numbers, and unsafe results are evaluation errors
    assert.equal(sum, 6);
    assert.equal(typeof sum, "number");
    assert.equal(decimal, 1.75);
    assert.deepEqual(table, [[5], [6], [7]]);
    assert.throws(
      () => adapter.evaluate(unsafe, {}),
      (error) => error instanceof CelEvaluationError && error.diagnostic.code === "invalid_result",
    );
    assert.throws(() => adapter.evaluate(bytes, {}), CelEvaluationError);
  });

  it("preserves an own __proto__ data member", () => {
    // given: an ordinary JSON context with an own __proto__ data member
    const adapter = createDefaultCelAdapter();
    const program = adapter.compile("payload");
    const context = JSON.parse('{"payload":{"__proto__":3}}');
    // when: CEL returns the object
    const result = adapter.evaluate(program, context);
    // then: the key remains own data on a null-prototype object
    assert.equal(Object.hasOwn(result, "__proto__"), true);
    assert.equal(Object.getPrototypeOf(result), null);
    assert.equal(result.__proto__, 3);
  });
});
