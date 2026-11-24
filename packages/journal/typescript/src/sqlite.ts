import {DatabaseSync} from "node:sqlite";

import type {FiringRecord, InjectionRecord} from "@velocitron/engine";

import {
  DEPOSIT_VIOLATION,
  FIRING,
  INJECTION,
  NET_REVISION,
  TRACE,
} from "./kinds.js";
import type {StoredEvent} from "./replay.js";
import {stringifyRecord} from "./serialize.js";

const SCHEMA = `
CREATE TABLE IF NOT EXISTS events (
    instance    TEXT    NOT NULL,
    seq         INTEGER NOT NULL,
    kind        TEXT    NOT NULL,
    payload     TEXT    NOT NULL,
    recorded_at TEXT    NOT NULL,
    PRIMARY KEY (instance, seq)
);
`;

export interface SqliteStatement {
  run(...params: readonly unknown[]): unknown;
  get(...params: readonly unknown[]): unknown;
  all(...params: readonly unknown[]): readonly unknown[];
}

/** The statement surface ``DurableJournal`` needs. ``openDatabase`` returns one. */
export interface SqliteDatabase {
  exec(sql: string): void;
  prepare(sql: string): SqliteStatement;
}

interface EventRow {
  seq: number;
  kind: string;
  payload: string;
  recorded_at?: string;
  max_seq?: number | null;
}

function asRow(value: unknown): EventRow {
  return value as EventRow;
}

/** Open (creating if absent) the event-log database in WAL mode. */
export function openDatabase(databasePath: string): SqliteDatabase {
  const database = new DatabaseSync(databasePath);
  database.exec("PRAGMA journal_mode=WAL");
  database.exec(SCHEMA);
  return database as unknown as SqliteDatabase;
}

/** Read one instance's events in sequence order, payloads decoded from JSON. */
export function readEvents(database: SqliteDatabase, instance: string): StoredEvent[] {
  const rows = database.prepare(
    "SELECT seq, kind, payload FROM events WHERE instance = ? ORDER BY seq",
  ).all(instance);
  return rows.map((row) => {
    const event = asRow(row);
    return {
      seq: event.seq,
      kind: event.kind,
      payload: JSON.parse(event.payload) as Record<string, unknown>,
    };
  });
}

/** Every instance that has at least one recorded event. */
export function knownInstances(database: SqliteDatabase): string[] {
  const rows = database.prepare(
    "SELECT DISTINCT instance FROM events ORDER BY instance",
  ).all();
  return rows.map((row) => String((row as {instance: string}).instance));
}

/**
 * A journal that appends one instance's records to sqlite.
 *
 * Each record is committed as it is appended. The instance name namespaces
 * one net's log within a shared database.
 */
export class DurableJournal {
  readonly #database: SqliteDatabase;
  readonly #instance: string;
  #seq: number;

  constructor(database: SqliteDatabase, instance: string) {
    this.#database = database;
    this.#instance = instance;
    const row = asRow(database.prepare(
      "SELECT MAX(seq) AS max_seq FROM events WHERE instance = ?",
    ).get(instance));
    this.#seq = row.max_seq === null || row.max_seq === undefined ? 0 : row.max_seq + 1;
  }

  recordFiring(record: FiringRecord): void {
    this.#append(FIRING, record);
  }

  recordDepositViolation(record: FiringRecord): void {
    this.#append(DEPOSIT_VIOLATION, record);
  }

  recordInjection(record: InjectionRecord): void {
    this.#append(INJECTION, record);
  }

  recordTrace(record: Readonly<Record<string, unknown>>): void {
    this.#append(TRACE, record);
  }

  recordNetRevision(netDocument: Readonly<Record<string, unknown>>): void {
    this.#append(NET_REVISION, netDocument);
  }

  #append(kind: string, record: unknown): void {
    this.#database.prepare(
      "INSERT INTO events(instance, seq, kind, payload, recorded_at) VALUES (?, ?, ?, ?, ?)",
    ).run(
      this.#instance,
      this.#seq,
      kind,
      stringifyRecord(record),
      new Date().toISOString(),
    );
    this.#seq += 1;
  }

  /** Payload plus ``kind``, ``sequence``, and ``recorded_at``, in seq order. */
  records(): ReadonlyArray<Record<string, unknown>> {
    const rows = this.#database.prepare(
      "SELECT seq, kind, payload, recorded_at FROM events WHERE instance = ? ORDER BY seq",
    ).all(this.#instance);
    return rows.map((row) => {
      const event = asRow(row);
      return {
        ...(JSON.parse(event.payload) as Record<string, unknown>),
        kind: event.kind,
        sequence: event.seq,
        recorded_at: event.recorded_at,
      };
    });
  }
}
