import { expect, test } from "bun:test";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { materializeSnapshot } from "./index";

test("metadata and redaction use one snapshot even if the file changes after parsing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-snapshot-"));

  try {
    const filePath = path.join(root, "profile.md");

    await writeFile(filePath, ("original " + ["sk", "proj", "abcdefghijklmnopqrstuv"].join("-")));

    const snapshot = await materializeSnapshot({
      filePath,
      roots: [root],
      maximumBytes: 1024,
      parse: (text) => {
        writeFileSync(filePath, "replacement");

        return text.startsWith("original");
      },
    });

    expect(snapshot?.parsed).toBeTrue();
    expect(snapshot?.redacted).toStartWith("original");
    expect(snapshot?.redacted).not.toContain("abcdefghijklmnopqrstuv");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
