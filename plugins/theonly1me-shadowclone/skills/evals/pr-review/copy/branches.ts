import { mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { git } from "../git";

async function treeWithoutWorkflows(options: { readonly clone: string; readonly commit: string }): Promise<string> {
  const directory = mkdtempSync(path.join(os.tmpdir(), "pr-review-index-"));
  const environment = { GIT_INDEX_FILE: path.join(directory, "index") };

  try {
    await git({ clone: options.clone, arguments: ["read-tree", options.commit], environment });
    await git({ clone: options.clone, arguments: ["rm", "--cached", "-r", "-q", "-f", "--ignore-unmatch", ".github/workflows"], environment });
    return await git({ clone: options.clone, arguments: ["write-tree"], environment });
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

export async function touchesWorkflows(options: { readonly clone: string; readonly base: string; readonly head: string }): Promise<boolean> {
  const changed = await git({ clone: options.clone, arguments: ["diff", "--name-only", `${options.base}...${options.head}`] });

  return changed.split("\n").some((file) => file.startsWith(".github/workflows/"));
}

export async function caseCommits(options: {
  readonly clone: string;
  readonly id: string;
  readonly upstream: number;
  readonly baseSha: string;
}): Promise<{ readonly base: string; readonly head: string }> {
  const { clone, id, upstream } = options;

  await git({ clone, arguments: ["fetch", "--quiet", "origin", `+refs/pull/${upstream}/head:refs/upstream-pulls/${upstream}`] });

  const upstreamHead = await git({ clone, arguments: ["rev-parse", `refs/upstream-pulls/${upstream}`] });
  const mergeBase = await git({ clone, arguments: ["merge-base", options.baseSha, upstreamHead] });

  if (await touchesWorkflows({ clone, base: mergeBase, head: upstreamHead })) {
    throw new Error(`upstream pull request ${upstream} changes workflows`);
  }

  const base = await git({
    clone,
    arguments: ["commit-tree", "-S", await treeWithoutWorkflows({ clone, commit: mergeBase }), "-p", mergeBase, "-m", `Case ${id} base`],
  });
  const head = await git({
    clone,
    arguments: ["commit-tree", "-S", await treeWithoutWorkflows({ clone, commit: upstreamHead }), "-p", base, "-m", `Case ${id} head`],
  });

  return { base, head };
}

export async function pushCase(options: { readonly clone: string; readonly remote: string; readonly id: string; readonly base: string; readonly head: string }): Promise<void> {
  await git({
    clone: options.clone,
    arguments: [
      "push",
      "--quiet",
      "--force",
      options.remote,
      `${options.base}:refs/heads/case-${options.id}/base`,
      `${options.head}:refs/heads/case-${options.id}/head`,
    ],
  });
}
