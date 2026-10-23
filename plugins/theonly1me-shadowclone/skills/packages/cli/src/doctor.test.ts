import { expect, test } from "bun:test";
import { renderEngineSelection, renderProviderSupport } from "./doctor";

test("reports provider support as two independent levels", () => {
  expect(renderProviderSupport()).toEqual([
    "claude-code: observe=yes, distill=yes",
    "codex: observe=yes, distill=yes",
    "cursor: observe=yes, distill=yes",
    "antigravity: observe=yes, distill=no",
    "pi: observe=yes, distill=yes",
  ]);
});

test("reports managed distillation policy separately from authentication", () => {
  expect(
    renderEngineSelection({
      distillation: "disabled",
      selectedEngine: null,
    }),
  ).toBe("Deep distillation is disabled by managed policy.");
  expect(
    renderEngineSelection({
      distillation: "local-only",
      selectedEngine: null,
    }),
  ).toBe(
    "Deep distillation is restricted to local engines, which are not implemented.",
  );
});
