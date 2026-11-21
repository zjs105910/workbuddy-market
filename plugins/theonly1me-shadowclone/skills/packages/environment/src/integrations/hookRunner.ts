import path from "node:path";
import { z } from "zod";
import { commitLocalChanges } from "@shadowclone/changes";
import { fingerprint, readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";

const ownerSchema = z.strictObject({ fingerprint: z.string() });

function shellQuote(value: string): string {
  return `'${value.replaceAll("'", "'\\''")}'`;
}

export async function ensureHookRunner(options: {
  readonly paths: ProjectPaths;
  readonly executable?: string;
  readonly entry?: string;
}): Promise<void> {
  const paths = options.paths;
  const filePath = path.join(paths.shadowcloneDirectory, "bin", "shadowclone");
  const ownerPath = path.join(paths.shadowcloneDirectory, "bin", "shadowclone-owner.json");
  const previous = await readLocalText(filePath);
  const ownerText = await readLocalText(ownerPath);
  const owner = ownerText === null ? null : ownerSchema.parse(JSON.parse(ownerText));

  if (previous !== null && owner?.fingerprint !== fingerprint(previous)) {
    throw new Error("The private hook launcher was edited; preserving it");
  }

  const entry = options.entry ?? process.argv[1];
  const executable = options.executable ?? process.execPath;
  const arguments_ = entry && path.isAbsolute(entry) &&
    /\.(?:mjs|js|ts)$/u.test(entry)
    ? [executable, entry]
    : [executable];
  const next = `exec ${arguments_.map(shellQuote).join(" ")} "$@"\n`;

  if (previous === next) {
    return;
  }

  await commitLocalChanges({
    paths,
    root: paths.shadowcloneDirectory,
    kind: "environment",
    updates: [
      { filePath, previous, next },
      {
        filePath: ownerPath,
        previous: ownerText,
        next: `${JSON.stringify({ fingerprint: fingerprint(next) })}\n`,
      },
    ],
  });
}
