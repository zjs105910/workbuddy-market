import { expect, test } from "bun:test";
import path from "node:path";
import { checkoutRoot } from "@shadowclone/core/testing";
import { preferenceEditFixture } from "@shadowclone/learning/testing";

test("the CLI keeps the complete replacement text in a preview", async () => {
  const { home, record } = await preferenceEditFixture();
  const process_ = Bun.spawn([process.execPath, path.join(import.meta.dir, "main.ts"), "learning", "replace", record.rule.key,
    "Use complete words for palette labels."], {
    cwd: await checkoutRoot(),
    env: { ...process.env, HOME: home }, stdout: "pipe", stderr: "pipe",
  });
  const [output, error, exitCode] = await Promise.all([
    new Response(process_.stdout).text(), new Response(process_.stderr).text(), process_.exited,
  ]);
  expect(error).toBe("");
  expect(exitCode).toBe(0);
  expect(output).toContain("Use complete words for palette labels.");
  expect(output).toContain("Preview only");
});
