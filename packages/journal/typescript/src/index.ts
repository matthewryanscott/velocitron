/**
 * Append, read, and replay a Velocitron journal.
 *
 * `InMemoryJournal` is the browser-safe memory adapter. `replayRecords`
 * rebuilds a marking from recorded firing and injection effects. No handlers
 * run. The Node sqlite adapter and the JSONL file flush live at
 * `@velocitron/journal/node` so this entry does not import a Node builtin.
 *
 * This package does not fire a net, run an async runtime, or import
 * `@velocitron/core`.
 */

export {
  DEPOSIT_VIOLATION,
  FIRING,
  INJECTION,
  NET_REVISION,
  TRACE,
} from "./kinds.js";
export {InMemoryJournal} from "./memory.js";
export {replayEvents, replayRecords} from "./replay.js";
export type {JournalRecordLike, StoredEvent} from "./replay.js";
export {serializeRecordValue} from "./serialize.js";
export type {
  FiringRecord,
  FiringStatus,
  InjectionKind,
  InjectionRecord,
  Journal,
  JournalRecord,
  SequencedJournalRecord,
  Marking,
  Net,
  Token,
} from "@velocitron/engine";
