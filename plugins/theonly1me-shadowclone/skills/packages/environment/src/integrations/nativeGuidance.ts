import path from "node:path";
import { maximumProfileBytes } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import { stripHarnessSection, stripManagedGuidance } from "./markdown";

const nativeGuidanceFiles = ["CLAUDE.md", "AGENTS.md"] as const;

export async function readNativeGuidance(options: {
  readonly cwd: string;
  readonly includeHarness: boolean;
}): Promise<readonly string[]> {
  const { cwd } = options;
  const texts: string[] = [];

  for (const filename of nativeGuidanceFiles) {
    const snapshot = await materializeSnapshot({
      filePath: path.join(cwd, filename),
      roots: [cwd],
      maximumBytes: maximumProfileBytes,
      parse: () => null,
    }).catch(() => null);
    const authored =
      snapshot === null ? "" : stripManagedGuidance(snapshot.redacted);
    const text = options.includeHarness
      ? authored
      : stripHarnessSection(authored);

    if (text.trim().length > 0) {
      texts.push(text);
    }
  }

  return texts;
}
