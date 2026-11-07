import { projectPaths } from "@shadowclone/core";
import { recallReferences } from "@shadowclone/profile";

export type RecallOptions = {
  readonly query: string;
  readonly limit: number;
};

export function parseRecallOptions(
  arguments_: readonly string[],
): RecallOptions | null {
  const query: string[] = [];
  let limit = 3;
  let sawLimit = false;

  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];

    if (argument === "--limit") {
      if (sawLimit) {
        return null;
      }

      const value = Number(arguments_[index + 1]);

      if (!Number.isInteger(value) || value < 1 || value > 10) {
        return null;
      }

      limit = value;
      sawLimit = true;
      index += 1;
      continue;
    }

    if (argument === undefined || argument.startsWith("--")) {
      return null;
    }

    query.push(argument);
  }

  const text = query.join(" ").trim();

  return text.length === 0 ? null : { query: text, limit };
}

export async function recallCommand(options: RecallOptions): Promise<void> {
  const result = await recallReferences({
    ...options,
    cwd: process.cwd(),
    paths: projectPaths,
  });

  if (result.records.length === 0) {
    await Bun.stdout.write("No matching references found.\n");

    return;
  }

  await Bun.stdout.write(`${result.records.join("\n")}\n`);

  if (result.omittedForBudget > 0) {
    await Bun.stdout.write(
      `${result.omittedForBudget} matching reference(s) omitted by the 64 KiB output budget.\n`,
    );
  }
}
