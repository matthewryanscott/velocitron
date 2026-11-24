import {
  InMemoryJournal,
  replayRecords,
  type Marking,
  type Net,
} from "./dist/index.js";

export function replayQuiet(net: Net, records: readonly Readonly<Record<string, unknown>>[]): Marking {
  const journal = new InMemoryJournal();
  return replayRecords(net, records.length === 0 ? journal.records : records);
}
