import type {ReadonlyJsonObject} from "./schema/types.js";

/**
 * Browser-safe synchronous CEL boundary. Compiled values are intentionally
 * opaque. This package does not ship a backend; pass an adapter.
 * The language implementation keeps its default adapter.
 */
export interface CelAdapter {
  compile(source: string): unknown;
  evaluate(compiled: unknown, context: ReadonlyJsonObject): unknown;
}
