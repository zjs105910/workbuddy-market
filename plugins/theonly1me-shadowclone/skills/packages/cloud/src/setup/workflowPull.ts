import { z } from "zod";
import type { Clone } from "../types";
import { renderWorkflows } from "../workflow";
import type { GithubApi } from "./github";

const shaSchema = z.object({ sha: z.string().regex(/^[a-f0-9]{40}$/) });

export function isCloneWorkflowPath(filePath: string): boolean {
  return (
    filePath.startsWith(".github/shadowclone/") ||
    [".github/workflows/shadowclone.yml", ".github/workflows/shadowclone-relay.yml"].includes(filePath)
  );
}

export async function readDefaultTree(options: {
  readonly clone: Clone;
  readonly token: string;
  readonly api: GithubApi;
}) {
  const { clone, token, api } = options;
  const base = `/repos/${clone.repository}`;
  const reference = z.object({ object: shaSchema }).parse(
    await api({ route: `GET ${base}/git/ref/heads/${encodeURIComponent(clone.defaultBranch)}`, token }),
  );
  const commit = z.object({ tree: shaSchema }).parse(
    await api({ route: `GET ${base}/git/commits/${reference.object.sha}`, token }),
  );
  const tree = z
    .object({ truncated: z.boolean(), tree: z.array(z.object({ path: z.string(), sha: z.string().optional() })) })
    .parse(await api({ route: `GET ${base}/git/trees/${commit.tree.sha}?recursive=1`, token }));

  return { headSha: reference.object.sha, treeSha: commit.tree.sha, tree };
}

export async function openWorkflowPull(options: {
  readonly clone: Clone;
  readonly token: string;
  readonly api: GithubApi;
  readonly parentSha: string;
  readonly baseTreeSha: string;
  readonly message: string;
  readonly branchPrefix: string;
  readonly body: string;
}): Promise<string> {
  const { clone, token, api } = options;
  const base = `/repos/${clone.repository}`;
  const tree = shaSchema.parse(
    await api({
      route: `POST ${base}/git/trees`,
      token,
      body: {
        base_tree: options.baseTreeSha,
        tree: Object.entries(renderWorkflows(clone)).map(([filePath, content]) => ({
          path: filePath,
          content,
          type: "blob",
          mode: "100644",
        })),
      },
    }),
  );
  const created = shaSchema.parse(
    await api({
      route: `POST ${base}/git/commits`,
      token,
      body: { message: options.message, tree: tree.sha, parents: [options.parentSha] },
    }),
  );
  const branch = `${options.branchPrefix}-${crypto.randomUUID()}`;

  await api({ route: `POST ${base}/git/refs`, token, body: { ref: `refs/heads/${branch}`, sha: created.sha } });

  const pull = z
    .object({ html_url: z.url().startsWith(`https://github.com/${clone.repository}/pull/`) })
    .parse(
      await api({
        route: `POST ${base}/pulls`,
        token,
        body: { title: options.message, body: options.body, head: branch, base: clone.defaultBranch, draft: true },
      }),
    );

  return pull.html_url;
}
