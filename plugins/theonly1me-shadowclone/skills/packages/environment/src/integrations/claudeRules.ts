import { existsSync } from "node:fs";
import { lstat, readdir } from "node:fs/promises";
import path from "node:path";
import { maximumProfileBytes } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";

const maximumRuleFiles = 128;
const maximumRuleBytes = 2_000_000;

async function markdownPaths(directory: string): Promise<readonly string[]> {
  if (!existsSync(directory)) {
    return [];
  }

  const root = await lstat(directory);

  if (!root.isDirectory() || root.isSymbolicLink()) {
    throw new Error("Claude rules directory is not a regular directory");
  }

  const files: string[] = [];
  const visit = async (current: string): Promise<void> => {
    for (const entry of (await readdir(current, { withFileTypes: true })).sort(
      (left, right) => left.name.localeCompare(right.name),
    )) {
      if (entry.isSymbolicLink()) {
        throw new Error("Claude rules contain a symbolic link");
      }

      const location = path.join(current, entry.name);

      if (entry.isDirectory()) {
        await visit(location);
      } else if (entry.isFile() && entry.name.endsWith(".md")) {
        files.push(location);

        if (files.length > maximumRuleFiles) {
          throw new Error("Claude rules exceed the file limit");
        }
      }
    }
  };

  await visit(directory);

  return files;
}

export async function readClaudeRules(cwd: string): Promise<readonly string[]> {
  const claudeDirectory = path.join(cwd, ".claude");

  if (existsSync(claudeDirectory)) {
    const parent = await lstat(claudeDirectory);

    if (!parent.isDirectory() || parent.isSymbolicLink()) {
      throw new Error(
        "Claude rules parent is not a regular directory or contains a symbolic link",
      );
    }
  }

  const directory = path.join(cwd, ".claude/rules");
  const texts: string[] = [];
  let bytes = 0;

  for (const filePath of await markdownPaths(directory)) {
    const snapshot = await materializeSnapshot({
      filePath,
      roots: [directory],
      maximumBytes: maximumProfileBytes,
      parse: () => null,
    });

    if (snapshot === null) {
      throw new Error("Claude rule changed during reading");
    }

    bytes += Buffer.byteLength(snapshot.redacted, "utf8");

    if (bytes > maximumRuleBytes) {
      throw new Error("Claude rules exceed the byte limit");
    }

    if (snapshot.redacted.trim()) {
      texts.push(snapshot.redacted);
    }
  }

  return texts;
}
