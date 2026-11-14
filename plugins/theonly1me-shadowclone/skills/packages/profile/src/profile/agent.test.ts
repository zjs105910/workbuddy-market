import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { writeAgent } from "./index";

test("writes a dispatchable agent with advisory boundaries", async () => {
  const targetDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-agent-"),
  );

  const profile = [
    "# Shadowclone profile",
    "",
    "## Requests confirmation after refusing Bash",
    "",
    "Ask before repeating a similar Bash action.",
  ].join("\n");

  const outputPath = await writeAgent({ targetDirectory, profile });
  const agent = await Bun.file(outputPath).text();

  expect(agent).toContain("name: shadowclone");
  expect(agent).toContain(profile);
});
