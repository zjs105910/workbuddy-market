import { mentionNames } from "../guard/comment";
import { reviewVersions } from "../workflow";
import type { Clone } from "../types";
import type { GithubApi } from "./github";
import { openWorkflowPull, readDefaultTree } from "./workflowPull";

export async function createReviewUpdatePull(options: {
  readonly clone: Clone;
  readonly token: string;
  readonly api: GithubApi;
}): Promise<string> {
  const { clone, token, api } = options;
  const [mention = "shadowclone"] = mentionNames(clone);
  const current = await readDefaultTree({ clone, token, api });

  if (current.tree.truncated) {
    throw new Error("The default branch tree is incomplete. Update the clone workflows by hand.");
  }

  const body = `## What changed

- [x] Render the clone workflows with Shadowclone ${reviewVersions.shadowclone}.
- [x] Add pull request reviews. A requester asks with \`@${mention} review\` on a pull request, and a requester's pull request gets one when it opens or becomes ready for review.

## Why

The clone reviews pull requests with this repository's standards, built-in rules, and toolchain, and posts one review as ${clone.botLogin}.

## Verification

1. Review the rendered workflows and guard helpers.
2. Merge this PR.
3. Comment \`@${mention} review\` on a pull request and confirm one review from ${clone.botLogin}.

## Data handling

The toolchain job runs the pull request's code without secrets. The review job holds only the Claude token and never runs that code. Only the publish job holds the App token.
`;

  return openWorkflowPull({
    clone,
    token,
    api,
    parentSha: current.headSha,
    baseTreeSha: current.treeSha,
    message: "ci: add pull request reviews to the github clone",
    branchPrefix: "shadowclone/update",
    body,
  });
}
