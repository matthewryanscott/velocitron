import {mkdirSync, writeFileSync} from "node:fs";
import {dirname} from "node:path";

import type {FiringRecord, InjectionRecord, Journal} from "@velocitron/engine";

import {stringifyRecord} from "./serialize.js";

/**
 * In-memory journal that can flush a timestamped ``.jsonl`` file.
 *
 * With no prefix, ``flush`` writes nothing. Sequence numbers are one
 * monotonic stream across firing, injection, trace, runtime, and net
 * revision records.
 */
export class JsonlJournal implements Journal {
  readonly #prefix: string | undefined;
  readonly #records: Array<Record<string, unknown>> = [];
  #sequence = 0;

  constructor(prefix?: string) {
    this.#prefix = prefix;
  }

  recordFiring(record: FiringRecord): void {
    this.#append(record);
  }

  recordDepositViolation(record: FiringRecord): void {
    this.#append(record);
  }

  recordInjection(record: InjectionRecord): void {
    this.#append(record);
  }

  recordTrace(record: Readonly<Record<string, unknown>>): void {
    this.#append(record);
  }

  recordRuntime(record: Readonly<Record<string, unknown>>): void {
    this.#append(record);
  }

  recordNetRevision(netDocument: Readonly<Record<string, unknown>>): void {
    this.#append(netDocument);
  }

  #append(record: object): void {
    this.#records.push({...record, sequence: this.#sequence});
    this.#sequence += 1;
  }

  records(): ReadonlyArray<Record<string, unknown>> {
    return this.#records.map((record) => ({...record}));
  }

  flush(): void {
    if (this.#prefix === undefined) return;
    const stamp = new Date().toISOString().replace(/[-:]/g, "").slice(0, 15);
    const path = `${this.#prefix}-${stamp}.jsonl`;
    mkdirSync(dirname(path), {recursive: true});
    const lines = this.#records.map((record) => stringifyRecord(record));
    writeFileSync(path, lines.length === 0 ? "" : `${lines.join("\n")}\n`, "utf8");
  }
}
