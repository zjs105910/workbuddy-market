import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { canonicalPath } from "@shadowclone/core";
import { scanClaudeMemoryDirectory } from "./scan";

function note(options: {
  readonly type: string | null;
  readonly body: string;
}): string {
  const metadata =
    options.type === null ? [] : ["metadata:", `  type: ${options.type}`];

  return [
    "---",
    "name: note",
    "description: A note",
    ...metadata,
    "---",
    "",
    options.body,
    "",
  ].join("\n");
}

async function memoryDirectory(
  files: Readonly<Record<string, string>>,
): Promise<string> {
  const directory = canonicalPath(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-memory-scan-")),
  );

  for (const [filename, content] of Object.entries(files)) {
    await Bun.write(path.join(directory, filename), content);
  }

  return directory;
}

test("memory kinds come from the user prefix or the frontmatter type", async () => {
  const directory = await memoryDirectory({
    "user_background.md": note({
      type: null,
      body: "Senior backend engineer.",
    }),
    "testing_notes.md": note({
      type: "feedback",
      body: "Run focused tests first.",
    }),
    "MEMORY.md": "# Memory Index\n",
  });

  try {
    const kinds = Object.fromEntries(
      (await scanClaudeMemoryDirectory(directory)).map((file) => [
        file.filename,
        file.kind,
      ]),
    );

    expect(kinds).toEqual({
      "MEMORY.md": "index",
      "testing_notes.md": "feedback",
      "user_background.md": "user",
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("a memory file without a known type still stops the scan", async () => {
  const directory = await memoryDirectory({
    "notes.md": note({ type: null, body: "Untyped." }),
  });

  try {
    await expect(scanClaudeMemoryDirectory(directory)).rejects.toThrow(
      "known memory type",
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
