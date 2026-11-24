/**
 * Node store adapters: sqlite and a JSONL file flush.
 *
 * Import this entry from Node. The package root stays free of Node builtins
 * so a browser can import `@velocitron/journal`.
 */

export {JsonlJournal} from "./jsonl.js";
export {
  DurableJournal,
  knownInstances,
  openDatabase,
  readEvents,
} from "./sqlite.js";
export type {SqliteDatabase, SqliteStatement} from "./sqlite.js";
export {
  DEPOSIT_VIOLATION,
  FIRING,
  INJECTION,
  InMemoryJournal,
  NET_REVISION,
  TRACE,
  replayEvents,
  replayRecords,
  serializeRecordValue,
} from "./index.js";
export type {
  FiringRecord,
  InjectionRecord,
  Journal,
  JournalRecordLike,
  Marking,
  Net,
  SequencedJournalRecord,
  StoredEvent,
  Token,
} from "./index.js";
