import { expect, test } from "bun:test";
import { buildFixture } from "@shadowclone/builds/testing";
import { readEnvironment } from "@shadowclone/environment";
import { createSkillDrafts } from "./skillDrafts";
import { generationResult, syntheticBrief } from "./fixtures";

test("provider failures retain their redacted diagnostic without changing a build", async () => {
  const context = await buildFixture();
  const secret = `sk-${"s".repeat(32)}`;
  const drafts = createSkillDrafts({
    ...context,
    engine: {
      engine: "claude-code",
      runner: async () => ({
        ...generationResult(null),
        isError: true,
        errorMessage: `Authentication rejected for token ${secret}`,
      }),
    },
  });

  const preview = await drafts.preview(syntheticBrief);
  const result = await drafts.generate({ id: preview.id }).then(
    () => "unexpected success",
    (error: unknown) =>
      error instanceof Error ? error.message : "unknown error",
  );

  expect(result).toContain("Authentication rejected");
  expect(result).not.toContain(secret);
  expect(await readEnvironment(context.paths)).toBeNull();
});
