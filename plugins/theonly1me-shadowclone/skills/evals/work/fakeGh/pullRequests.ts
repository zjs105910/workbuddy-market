import { ensureChecks, latestRuns, rollupConclusion } from "./checks";
import { currentBranch, mergesCleanly, remoteHead } from "./git";
import type { FakeState, PullRequest, Release, Workspace } from "./state";

export function releaseThreads(options: {
  readonly state: FakeState;
  readonly pullRequest: number;
  readonly trigger: Release;
}): void {
  for (const thread of options.state.threads) {
    if (thread.pullRequest === options.pullRequest && thread.release === options.trigger) {
      thread.released = true;
    }
  }
}

export function refresh(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
}): void {
  for (const pullRequest of options.state.pullRequests) {
    if (pullRequest.state !== "OPEN") {
      continue;
    }

    const head = remoteHead({ remoteDirectory: options.workspace.remoteDirectory, branch: pullRequest.head });

    if (head === null) {
      continue;
    }

    if (pullRequest.initialHead === null) {
      pullRequest.initialHead = head;
    } else if (pullRequest.initialHead !== head) {
      releaseThreads({ state: options.state, pullRequest: pullRequest.number, trigger: "head-changed" });
    }

    ensureChecks({ workspace: options.workspace, state: options.state, sha: head });
  }
}

export function findPullRequest(options: {
  readonly state: FakeState;
  readonly selector: string | undefined;
  readonly cwd: string;
}): PullRequest | undefined {
  const selector = options.selector ?? currentBranch(options.cwd) ?? "";
  const number = Number(selector.replace(/^#/, "").split("/").at(-1));

  return (
    options.state.pullRequests.find((candidate) => Number.isInteger(number) && candidate.number === number) ??
    options.state.pullRequests.find((candidate) => candidate.head === selector && candidate.state === "OPEN") ??
    options.state.pullRequests.find((candidate) => candidate.head === selector)
  );
}

export function pullRequestUrl(options: {
  readonly state: FakeState;
  readonly number: number;
}): string {
  return `https://github.com/${options.state.repository.owner}/${options.state.repository.name}/pull/${options.number}`;
}

export function checkRollup(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly pullRequest: PullRequest;
}): readonly Readonly<Record<string, unknown>>[] {
  const head = remoteHead({ remoteDirectory: options.workspace.remoteDirectory, branch: options.pullRequest.head });

  if (head === null) {
    return [];
  }

  return latestRuns({ state: options.state, sha: head }).map((run) => ({
    __typename: "CheckRun",
    name: run.job,
    workflowName: "ci",
    status: "COMPLETED",
    conclusion: run.conclusion === "success" ? "SUCCESS" : "FAILURE",
    state: run.conclusion === "success" ? "SUCCESS" : "FAILURE",
    bucket: run.conclusion === "success" ? "pass" : "fail",
    link: `${pullRequestUrl({ state: options.state, number: options.pullRequest.number })}/checks?run=${run.id}`,
    detailsUrl: `https://github.com/${options.state.repository.owner}/${options.state.repository.name}/actions/runs/${run.id}`,
    databaseId: run.id,
  }));
}

export function pullRequestRecord(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly pullRequest: PullRequest;
}): Readonly<Record<string, unknown>> {
  const { pullRequest, workspace, state } = options;
  const head = remoteHead({ remoteDirectory: workspace.remoteDirectory, branch: pullRequest.head }) ?? "";
  const base = remoteHead({ remoteDirectory: workspace.remoteDirectory, branch: pullRequest.base }) ?? "";
  const clean = head !== "" && base !== "" && mergesCleanly({ gitDirectory: workspace.remoteDirectory, base, head });
  const conclusion = rollupConclusion(head === "" ? [] : latestRuns({ state, sha: head }));
  const openThreads = state.threads.filter((thread) => thread.pullRequest === pullRequest.number && thread.released && !thread.resolved);

  return {
    number: pullRequest.number,
    title: pullRequest.title,
    body: pullRequest.body,
    state: pullRequest.state,
    isDraft: pullRequest.draft,
    headRefName: pullRequest.head,
    baseRefName: pullRequest.base,
    headRefOid: head,
    url: pullRequestUrl({ state, number: pullRequest.number }),
    author: { login: state.viewer },
    mergeable: clean ? "MERGEABLE" : "CONFLICTING",
    mergeStateStatus: !clean ? "DIRTY" : conclusion === "failure" ? "UNSTABLE" : pullRequest.draft ? "DRAFT" : "CLEAN",
    reviewDecision: pullRequest.approved ? "APPROVED" : "REVIEW_REQUIRED",
    statusCheckRollup: checkRollup({ workspace, state, pullRequest }),
    comments: state.topLevelComments
      .filter((comment) => comment.pullRequest === pullRequest.number)
      .map((comment) => ({ author: { login: comment.author }, body: comment.body })),
    reviews: [
      ...(pullRequest.approved ? [{ author: { login: "teammate" }, body: "LGTM", state: "APPROVED" }] : []),
      ...state.threads
        .filter((thread) => thread.pullRequest === pullRequest.number && thread.released)
        .flatMap((thread) => thread.comments.slice(0, 1))
        .map((comment) => ({ author: { login: comment.author }, body: comment.body, state: "COMMENTED" })),
    ],
    unresolvedThreadCount: openThreads.length,
  };
}
