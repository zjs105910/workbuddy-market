import { createHash } from "node:crypto";
import type { Clone } from "../types";
import { renderWorkflows } from "../workflow";
import type { GithubApi } from "./github";
import { isCloneWorkflowPath, openWorkflowPull, readDefaultTree } from "./workflowPull";

function blobSha(content: string): string {
  const bytes = Buffer.from(content);

  return createHash("sha1").update(`blob ${bytes.length}\0`).update(bytes).digest("hex");
}

function identityLine(clone: Clone): string {
  return clone.identity.kind === "account"
    ? `Commits, pull requests, and reviews come from the machine account ${clone.botLogin}. Mention @${clone.botLogin} to start work.`
    : `Commits, pull requests, and reviews come from the App ${clone.botLogin}. Mention @shadowclone to start work.`;
}

function pullBody(options: { readonly clone: Clone; readonly update: boolean }): string {
  const { clone } = options;

  return `## What changed

- [x] ${options.update ? "Render" : "Add"} the Shadowclone workflows for ${clone.botLogin}.
- [x] Read the reviewed skills from the private repository ${clone.skillsRepository} with a read-only deploy key.

## Why

${identityLine(clone)}

## Verification

1. Review both workflows and the guard helpers.
2. Check that the \`shadowclone\` environment has every secret that \`shadowclone bot status\` lists.
3. Merge this pull request, then open a small issue and mention the bot in it.

## Data handling

The tokens and the deploy key are secrets in the \`shadowclone\` environment, which only ${clone.defaultBranch} can use. The default-branch workflows and the code that runs with those secrets remain trusted.
`;
}

export async function openWorkflowChange(options: {
  readonly clone: Clone;
  readonly api: GithubApi;
  readonly token?: string;
}): Promise<string | null> {
  const { clone, api } = options;
  const token = options.token ?? "";
  const current = await readDefaultTree({ clone, token, api });

  if (current.tree.truncated) {
    throw new Error("The default branch tree is incomplete. Review the workflows by hand before setup.");
  }

  const installed = new Map(current.tree.tree.filter((entry) => isCloneWorkflowPath(entry.path)).map((entry) => [entry.path, entry.sha]));
  const update = installed.size > 0;
  const changed = Object.entries(renderWorkflows(clone)).some(([filePath, content]) => installed.get(filePath) !== blobSha(content));

  if (!changed) {
    return null;
  }

  return openWorkflowPull({
    clone,
    token,
    api,
    parentSha: current.headSha,
    baseTreeSha: current.treeSha,
    message: update ? "ci: update the shadowclone workflows" : "ci: configure the shadowclone bot",
    branchPrefix: update ? "shadowclone/update" : "shadowclone/setup",
    body: pullBody({ clone, update }),
  });
}
