import path from "node:path";
import { readLocalText, projectPaths } from "@shadowclone/core";
import {
  migrateClaudeMemory,
  parseClaudeMemoryDecisions,
  type ClaudeMemoryDecisions,
  type ClaudeMemoryMigrationResult,
} from "@shadowclone/profile";
import { readEnvironment } from "@shadowclone/environment";

type MigrationOptions = {
  readonly apply: boolean;
  readonly decisionsPath: string | null;
};

function parseOptions(arguments_: readonly string[]): MigrationOptions | null {
  let apply = false;
  let decisionsPath: string | null = null;

  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];

    if (argument === "--apply" && !apply) {
      apply = true;
      continue;
    }

    if (argument === "--decisions" && decisionsPath === null) {
      const value = arguments_[index + 1];

      if (value === undefined) {
        return null;
      }

      decisionsPath = path.resolve(value);
      index += 1;
      continue;
    }

    return null;
  }

  return { apply, decisionsPath };
}

async function readDecisions(
  filePath: string | null,
): Promise<ClaudeMemoryDecisions | undefined> {
  if (filePath === null) {
    return undefined;
  }

  const text = await readLocalText(filePath);

  if (text === null) {
    throw new Error("Claude memory decisions file was not found");
  }

  return parseClaudeMemoryDecisions(text);
}

export function renderMigrationResult(
  result: ClaudeMemoryMigrationResult,
): string {
  const counts = Map.groupBy(
    result.plan.manifest.files,
    (file) => file.disposition,
  );
  const lines = [
    `Claude memory migration: ${result.plan.manifest.files.length} file(s).`,
    ...[...counts]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([disposition, files]) => `  ${disposition}: ${files.length}`),
    ...(result.plan.reviewRequired.length === 0
      ? []
      : [
          "Feedback requiring reviewed dispositions:",
          ...result.plan.reviewRequired.map((filename) => `  ${filename}`),
        ]),
  ];

  if (result.plan.alreadyApplied) {
    lines.push("This source snapshot was already migrated.");
  } else if (result.revisionId !== null) {
    lines.push(`Applied revision ${result.revisionId}.`);
  } else {
    lines.push(
      "Preview only. Use --decisions <file> --apply after reviewing feedback.",
    );
  }

  lines.push("Native Claude memory is never changed or removed.");

  return `${lines.join("\n")}\n`;
}

export async function handleMigrateCommand(options: {
  readonly command: string | undefined;
  readonly arguments: readonly string[];
}): Promise<boolean> {
  if (
    options.command !== "migrate" ||
    options.arguments[0] !== "claude-memory"
  ) {
    return false;
  }

  const parsed = parseOptions(options.arguments.slice(1));

  if (await readEnvironment(projectPaths)) {
    throw new Error(
      "Use migrate skills --apply --memory for recurring memory extraction into the learning environment.",
    );
  }

  if (parsed === null) {
    throw new Error(
      "Use shadowclone migrate claude-memory [--decisions <file>] [--apply]",
    );
  }

  const result = await migrateClaudeMemory({
    paths: projectPaths,
    cwd: process.cwd(),
    apply: parsed.apply,
    decisions: await readDecisions(parsed.decisionsPath),
  });

  await Bun.stdout.write(renderMigrationResult(result));

  return true;
}
