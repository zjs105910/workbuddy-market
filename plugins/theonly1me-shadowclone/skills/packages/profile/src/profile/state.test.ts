import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { readProfileFiles } from "./files";
import { readGeneratedProfileState } from "./state";

test("ignores state paths outside the profile directory", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-state-"));
  const statePath = path.join(directory, ".generated");

  await Bun.write(
    statePath,
    [
      "../../outside.md\tlegacy-key",
      JSON.stringify({
        schema: 1,
        relativePath: "../outside.md",
        key: "current-key",
        title: "Outside",
        body: "Outside the profile.",
        source: "mined",
        disposition: "present",
      }),
    ].join("\n"),
  );

  await expect(readGeneratedProfileState(statePath)).rejects.toThrow(
    "invalid entry",
  );
});

test("refuses routed profile paths outside the closed directory shape", async () => {
  const profileDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-path-"),
  );

  const invalidPaths = [
    "/tmp",
    "/login",
    "global",
    "../outside.md",
    "org/owner/../../outside.md",
    "org\\..\\outside.md",
  ];

  for (const relativePath of invalidPaths) {
    await expect(
      readProfileFiles({ profileDirectory, relativePaths: [relativePath] }),
    ).rejects.toThrow("invalid relative path");
  }
});
