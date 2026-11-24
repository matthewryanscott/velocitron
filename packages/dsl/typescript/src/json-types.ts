/**
 * JSON types the lowerer needs. `python3 tools/dsl_package.py` points the
 * copied lowerer at this file instead of `@velocitron/core`'s schema types.
 * The shapes match `JsonValue` and `ReadonlyJsonObject` there.
 */

export type JsonPrimitive = null | boolean | number | string;

export type JsonValue = JsonPrimitive | readonly JsonValue[] | ReadonlyJsonObject;

export interface ReadonlyJsonObject {
  readonly [key: string]: JsonValue;
}
