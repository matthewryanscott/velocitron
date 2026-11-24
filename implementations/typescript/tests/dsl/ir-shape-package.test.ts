// @ts-expect-error -- Node globals are provided by the Vitest process; the
// browser-safe production package intentionally does not depend on @types/node.
import {readFileSync} from "node:fs";
// @ts-expect-error -- See the node:fs import above.
import {fileURLToPath} from "node:url";
import {describe, expect, it} from "vitest";
import {resolveContributionIr} from "@velocitron/petrinet";
import {loadContributionIr} from "../../../../packages/ir/typescript/index.js";

const cadencePath = fileURLToPath(
  new URL(
    "../../../../packages/spec/conformance/petrinet/12-reading-hour-fragment/reading_cadence.contribution-ir.json",
    import.meta.url,
  ),
);
const cadenceCel = "clock.now >= latch.fired_at + latch.cadence_s";

function celStrings(value: unknown, found: string[] = []): string[] {
  if (Array.isArray(value)) {
    for (const item of value) celStrings(item, found);
    return found;
  }
  if (typeof value === "object" && value !== null) {
    for (const [key, item] of Object.entries(value)) {
      if (key === "cel" && typeof item === "string") found.push(item);
      else celStrings(item, found);
    }
  }
  return found;
}

describe("contribution IR shape package", () => {
  it("keeps CEL text and still resolves through @velocitron/petrinet", () => {
    // given: the source-tree shape loader and a conformance contribution-IR net
    const document: unknown = JSON.parse(readFileSync(cadencePath, "utf8"));
    // when: the shape loader validates it and the implementation resolver decodes it
    const loaded = loadContributionIr(document);
    const resolved = resolveContributionIr(loaded);
    // then: CEL text is unchanged on the IR, and resolution still yields the net
    expect(celStrings(loaded)).toContain(cadenceCel);
    expect(resolved).toHaveProperty("places");
    expect(resolved).not.toHaveProperty("format", "velocitron.petrinet/contribution-ir");
  });
});
