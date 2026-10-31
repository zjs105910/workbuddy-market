import path from "node:path";
import { z } from "zod";
import { fingerprint, readLocalText, replaceLocalText } from "@shadowclone/core";
import {
  scanClaudeMemory,
  type ClaudeMemoryFile,
} from "@shadowclone/profile";
import type { ProjectPaths } from "@shadowclone/core";
import type { ProfileRule } from "@shadowclone/profile";
import type { RepositoryIdentity } from "@shadowclone/sessions";
import { writeProfile } from "@shadowclone/environment";

const ledgerSchema = z.strictObject({
  version: z.literal(1),
  repositories: z.record(
    z.string(),
    z.record(
      z.string(),
      z.strictObject({
        hash: z.string(),
        decision: z.enum(["promoted", "declined"]),
      }),
    ),
  ),
});
type MemoryLedger = z.infer<typeof ledgerSchema>;

function ledgerPath(paths: ProjectPaths): string {
  return path.join(paths.shadowcloneDirectory, "harness-memory.json");
}

async function readLedger(paths: ProjectPaths): Promise<MemoryLedger> {
  const text = await readLocalText(ledgerPath(paths));

  if (text === null) {
    return { version: 1, repositories: {} };
  }

  try {
    return ledgerSchema.parse(JSON.parse(text));
  } catch {
    throw new Error("Invalid harness memory state");
  }
}

export function memoryTitle(file: ClaudeMemoryFile): string {
  const named = (file.name || file.filename.replace(/\.md$/, ""))
    .replace(/^(?:feedback|user)_/, "")
    .replaceAll(/[_-]+/g, " ")
    .trim();
  const title = file.description.trim() || named || file.filename;

  return title.length > 96 ? `${title.slice(0, 93).trimEnd()}...` : title;
}

export async function memoryCandidates(options: {
  readonly paths: ProjectPaths;
  readonly root: string;
  readonly repository: RepositoryIdentity;
}): Promise<readonly ClaudeMemoryFile[]> {
  const decided =
    (await readLedger(options.paths)).repositories[
      fingerprint(options.repository.id)
    ] ?? {};
  const files = await scanClaudeMemory({
    paths: options.paths,
    repositoryRoot: options.root,
  });

  return files.filter(
    (file) =>
      (file.kind === "feedback" || file.kind === "user") &&
      decided[file.filename]?.hash !== file.hash,
  );
}

export async function recordMemoryDecision(options: {
  readonly paths: ProjectPaths;
  readonly repository: RepositoryIdentity;
  readonly file: ClaudeMemoryFile;
  readonly promote: boolean;
}): Promise<string | null> {
  let key: string | null = null;

  if (options.promote) {
    const location = options.repository.profileFileName
      ? {
          scope: "project" as const,
          originDirectory: options.repository.origin.directoryName,
          repositoryName: options.repository.profileFileName,
        }
      : {
          scope: "org" as const,
          originDirectory: options.repository.origin.directoryName,
          repositoryName: null,
        };
    const rule: ProfileRule = {
      ...location,
      key: `claude-memory:${options.file.filename.replace(/\.md$/, "")}`,
      title: memoryTitle(options.file),
      body: options.file.body.trim(),
      section: "engineering",
      source: "declared",
      status: "active",
      proposal: null,
      appliesWhen: [],
      evidence: { for: [], against: [] },
      observations: 0,
      sessions: 0,
      lastSeen: new Date().toISOString(),
      origins: [],
      importReference: null,
    };

    await writeProfile({ paths: options.paths, rules: [rule] });
    key = rule.key;
  }

  const filePath = ledgerPath(options.paths);
  const previous = await readLocalText(filePath);
  const ledger = await readLedger(options.paths);

  const repositoryKey = fingerprint(options.repository.id);
  const decisions = {
    ...ledger.repositories[repositoryKey],
    [options.file.filename]: {
      hash: options.file.hash,
      decision: options.promote ? ("promoted" as const) : ("declined" as const),
    },
  };

  await replaceLocalText({
    filePath,
    previous,
    next: `${JSON.stringify({ ...ledger, repositories: { ...ledger.repositories, [repositoryKey]: decisions } }, null, 2)}\n`,
  });

  return key;
}
