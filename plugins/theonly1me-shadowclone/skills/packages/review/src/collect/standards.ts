import path from "node:path";
import { redactSecrets } from "@shadowclone/redact";
import { readGit } from "./git";

export type StandardsDocument = {
  readonly path: string;
  readonly text: string;
};

export type Standards = {
  readonly documents: readonly StandardsDocument[];
  readonly omitted: readonly string[];
};

type TreeEntry = {
  readonly path: string;
  readonly object: string;
  readonly size: number;
};

const instructionFileNames = ["AGENTS.md", "CLAUDE.md", "GEMINI.md"] as const;
const maximumDocumentBytes = 100_000;
const maximumStandardsBytes = 80_000;

const supportingPathsInPriorityOrder: readonly RegExp[] = [
  /^\.claude\/rules\/.+\.md$/,
  /^\.shadowclone\/harness\.json$/,
  /^(?:\.github\/|docs\/)?CONTRIBUTING\.md$/,
  /^\.github\/copilot-instructions\.md$/,
  /^\.github\/instructions\/.+\.instructions\.md$/,
  /^\.cursor\/rules\/.+\.mdc?$/,
  /^\.cursorrules$/,
  /^\.(?:claude|agents)\/skills\/[^/]+\/SKILL\.md$/,
];

function parseTree(output: string): readonly TreeEntry[] {
  return output.split("\0").flatMap((record) => {
    const match = /^(100644|100755) blob ([a-f0-9]{40,64}) +(\d+)\t(.+)$/.exec(record);

    return match?.[2] && match[3] && match[4]
      ? [{ object: match[2], size: Number(match[3]), path: match[4] }]
      : [];
  });
}

function ancestorDirectories(changedPaths: readonly string[]): ReadonlySet<string> {
  const directories = new Set([""]);

  for (const changedPath of changedPaths) {
    let directory = path.posix.dirname(changedPath);

    while (directory !== "." && directory !== "/") {
      directories.add(directory);
      directory = path.posix.dirname(directory);
    }
  }

  return directories;
}

function isInstructionFile(entryPath: string): boolean {
  return instructionFileNames.some((name) => path.posix.basename(entryPath) === name);
}

function selectEntries(options: {
  readonly entries: readonly TreeEntry[];
  readonly changedPaths: readonly string[];
}): readonly TreeEntry[] {
  const directories = ancestorDirectories(options.changedPaths);
  const instructionEntries = options.entries
    .filter((entry) => isInstructionFile(entry.path))
    .filter((entry) => {
      const directory = path.posix.dirname(entry.path);

      return directories.has(directory === "." ? "" : directory);
    })
    .sort((left, right) => left.path.split("/").length - right.path.split("/").length);
  const supportingEntries = supportingPathsInPriorityOrder.flatMap((pattern) =>
    options.entries.filter((entry) => pattern.test(entry.path)),
  );

  return [...instructionEntries, ...supportingEntries];
}

export async function readStandards(options: {
  readonly checkout: string;
  readonly baseSha: string;
  readonly changedPaths: readonly string[];
}): Promise<Standards> {
  const tree = parseTree(
    await readGit({
      checkout: options.checkout,
      arguments: ["ls-tree", "-r", "-l", "-z", "--full-tree", options.baseSha],
    }),
  );
  const documents: StandardsDocument[] = [];
  const omitted: string[] = [];
  let totalBytes = 0;

  for (const entry of selectEntries({ entries: tree, changedPaths: options.changedPaths })) {
    if (entry.size > maximumDocumentBytes || totalBytes + entry.size > maximumStandardsBytes) {
      omitted.push(entry.path);
      continue;
    }

    const text = await readGit({
      checkout: options.checkout,
      arguments: ["cat-file", "blob", entry.object],
    });

    totalBytes += entry.size;
    documents.push({ path: entry.path, text: redactSecrets({ text }) });
  }

  return { documents, omitted };
}
