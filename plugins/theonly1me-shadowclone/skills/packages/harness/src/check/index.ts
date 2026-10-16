import { lstat } from "node:fs/promises";
import path from "node:path";
import { runCommand, type CommandRunner, canonicalPath } from "@shadowclone/core";
import { readHarnessManifest } from "@shadowclone/environment";
import { loadRepositoryCommentReader } from "./comments";
import { conventionFindings, fileExtension } from "./conventions";
import { listCheckFiles } from "./files";
import { healthFindings } from "./health";
import type { HarnessCheckReport, HarnessFinding } from "./types";

export type { HarnessCheckReport, HarnessFinding } from "./types";
export { renderCheckReport, type CheckFormat } from "./render";

const checkedProseExtensions = [
  ".md",
  ".mdx",
  ".txt",
  ".yml",
  ".yaml",
  ".json",
  ".toml",
];
const maximumCheckedBytes = 1_000_000;

export async function repositoryRoot(options: {
  readonly cwd: string;
  readonly runner?: CommandRunner;
}): Promise<string> {
  const result = await (options.runner ?? runCommand)({
    command: ["git", "rev-parse", "--show-toplevel"],
    cwd: options.cwd,
  });
  const top = result.stdout.trim();

  return canonicalPath(
    result.exitCode === 0 && top.length > 0 ? top : options.cwd,
  );
}

async function readCheckedText(filePath: string): Promise<string | null> {
  const metadata = await lstat(filePath).catch(() => null);

  if (
    metadata === null ||
    !metadata.isFile() ||
    metadata.isSymbolicLink() ||
    metadata.size > maximumCheckedBytes
  ) {
    return null;
  }

  return Bun.file(filePath).text();
}

export async function runHarnessCheck(options: {
  readonly root: string;
  readonly changed: boolean;
  readonly runner?: CommandRunner;
}): Promise<HarnessCheckReport> {
  const manifest = await readHarnessManifest(options.root);

  if (manifest === null) {
    return {
      checkedFiles: 0,
      findings: [
        {
          severity: "error",
          rule: "harness-missing",
          path: ".shadowclone/harness.json",
          line: null,
          fix: "This repository has no Shadowclone setup. Run `shadowclone init --repo` to create one.",
        },
      ],
    };
  }

  const findings: HarnessFinding[] = [
    ...(await healthFindings({ root: options.root, manifest })),
  ];

  const relevant = new Set([
    ...manifest.sourceExtensions,
    ...checkedProseExtensions,
  ]);
  const files = (
    await listCheckFiles({
      root: options.root,
      changed: options.changed,
      runner: options.runner,
    })
  ).filter(
    (file) =>
      relevant.has(fileExtension(file)) && file !== ".shadowclone/harness.json",
  );

  const needsComments = manifest.conventions.some(
    (convention) =>
      convention.kind === "no-comments" ||
      convention.kind === "no-suppressions",
  );
  const readComments = needsComments
    ? await loadRepositoryCommentReader(options.root)
    : null;

  if (
    readComments === null &&
    manifest.conventions.some((convention) => convention.kind === "no-comments")
  ) {
    findings.push({
      severity: "warning",
      rule: "typescript-unavailable",
      path: "package.json",
      line: null,
      fix: "Install dependencies so shadowclone check can use the repository's typescript package to find comments.",
    });
  }

  let checkedFiles = 0;

  for (const file of files) {
    const text = await readCheckedText(path.join(options.root, file));

    if (text === null) {
      continue;
    }

    checkedFiles += 1;
    findings.push(
      ...conventionFindings({
        path: file,
        text,
        conventions: manifest.conventions,
        sourceExtensions: manifest.sourceExtensions,
        readComments,
      }),
    );
  }

  return { checkedFiles, findings };
}
