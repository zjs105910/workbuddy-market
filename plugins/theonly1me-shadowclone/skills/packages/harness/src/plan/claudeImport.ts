import { stripHarnessSection } from "@shadowclone/environment";
import { importsAgentsFile, planManagedFile, type PlannedFile } from "./files";

export async function planClaudeImport(options: {
  readonly root: string;
  readonly expected: string | undefined;
}): Promise<readonly PlannedFile[]> {
  const planned = await planManagedFile({
    root: options.root,
    relativePath: "CLAUDE.md",
    initial: "# Claude instructions",
    body: "@AGENTS.md",
    expected: options.expected,
    reason: "imports AGENTS.md so Claude reads the same map",
  });

  if (
    planned.status === "preserved" ||
    planned.status === "skipped" ||
    options.expected !== undefined
  ) {
    return [planned];
  }

  const importsAlready = importsAgentsFile(
    planned.previous === null ? null : stripHarnessSection(planned.previous),
  );

  return importsAlready
    ? [
        {
          ...planned,
          status: "skipped",
          next: null,
          fingerprint: null,
          reason: "already imports AGENTS.md",
        },
      ]
    : [planned];
}
