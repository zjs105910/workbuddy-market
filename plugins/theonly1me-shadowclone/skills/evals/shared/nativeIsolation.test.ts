import { expect, test } from "bun:test";
import path from "node:path";
import { managedEnd, managedStart } from "@shadowclone/environment";
import { integrationFixture } from "@shadowclone/core/testing";
import { isolateNativeGuidance } from "./nativeIsolation";

test("isolates generated sections from nested evaluation instructions before either arm runs", async () => {
  const fixture = await integrationFixture();
  const filePath = path.join(fixture.cwd, "nested/AGENTS.md");
  const original = "# Nested instructions\n\nKeep this user guidance.\n";

  await Bun.write(
    filePath,
    `${original}${managedStart}\n# Shadowclone profile\n\nGenerated rule\n${managedEnd}`,
  );
  await isolateNativeGuidance(fixture.cwd);

  expect(await Bun.file(filePath).text()).toBe(original);
});
