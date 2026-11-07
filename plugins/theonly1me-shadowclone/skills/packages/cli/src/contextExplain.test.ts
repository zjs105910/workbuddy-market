import { expect, test } from "bun:test";
import path from "node:path";
import { compileContextDetails } from "@shadowclone/environment";
import { integrationFixture } from "@shadowclone/core/testing";
import { renderStartupContextSummary } from "./contextExplain";

test("the startup summary counts omitted rules by reason without printing rule text", async () => {
  const fixture = await integrationFixture();
  const rules = Array.from(
    { length: 400 },
    (_, index) =>
      `## Rule ${index}\n\nKeep behavior ${"x".repeat(60)} number ${index}.\n`,
  );

  await Bun.write(
    path.join(fixture.paths.profileDirectory, "global/workflow.md"),
    rules.join("\n"),
  );

  const summary = renderStartupContextSummary(
    await compileContextDetails({
      ...fixture,
      format: "index",
      nativeDuplicates: "including-harness",
    }),
  );

  expect(summary).toMatch(
    /^Session-start context here: \d+ rule line\(s\), \d+\/4096 bytes; omitted: \d+ budget\.$/,
  );
  expect(summary).not.toContain("Keep behavior");
  expect(renderStartupContextSummary(null)).toBe(
    "Session-start context: disabled by policy.",
  );
});
