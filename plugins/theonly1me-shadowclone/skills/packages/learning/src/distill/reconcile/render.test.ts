import { expect, test } from "bun:test";
import { renderReconciliationChanges } from "./render";

test("a learning pass that only dropped rules names each one instead of reporting no changes", () => {
  const output = renderReconciliationChanges({
    changes: [],
    droppedRules: [
      { title: "Session telemetry", reason: "It records activity, not guidance." },
      { title: "Tool counts", reason: "It repeats session statistics." },
    ],
  });

  expect(output).toBe(
    [
      "2 learned rules were dropped while merging:",
      "- Session telemetry: It records activity, not guidance.",
      "- Tool counts: It repeats session statistics.",
    ].join("\n"),
  );
});

test("a learning pass with no changes and no drops says so", () => {
  expect(renderReconciliationChanges({ changes: [], droppedRules: [] })).toBe(
    "No profile changes proposed.",
  );
});
