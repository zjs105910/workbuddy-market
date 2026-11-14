import { commitTouches, isAncestor, remoteHead } from "../fakeGh/git";
import type { FakeState, Workspace } from "../fakeGh/state";
import type { CaseThread } from "../scaffold/definition";

const shaReply = /^[0-9a-f]{40}( [0-9a-f]{40})*$/;

export type ThreadVerdict = {
  readonly id: string;
  readonly expected: CaseThread["expected"];
  readonly passed: boolean;
  readonly reason: string;
};

function judgeFix(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly thread: CaseThread;
  readonly replies: readonly string[];
  readonly resolved: boolean;
}): string | null {
  const { workspace, state, thread, replies, resolved } = options;
  const [reply] = replies;

  if (replies.length !== 1 || reply === undefined) {
    return `expected one reply, found ${replies.length}`;
  }

  if (!shaReply.test(reply.trim())) {
    return "reply is not only full commit SHAs";
  }

  const branch = state.pullRequests.find((pullRequest) => pullRequest.number === thread.pullRequest)?.head ?? "";
  const head = remoteHead({ remoteDirectory: workspace.remoteDirectory, branch });

  if (head === null) {
    return "pull request branch is missing on the remote";
  }

  const shas = reply.trim().split(" ");

  if (!shas.every((sha) => isAncestor({ gitDirectory: workspace.remoteDirectory, ancestor: sha, descendant: head }))) {
    return "a replied SHA is not in the pull request's final branch";
  }

  if (!shas.some((sha) => commitTouches({ gitDirectory: workspace.remoteDirectory, commit: sha, path: thread.path }))) {
    return "no replied commit touches the commented file";
  }

  if (resolved !== thread.bot) {
    return thread.bot ? "fixed bot thread was not resolved" : "human thread was resolved";
  }

  return null;
}

export function judgeThreads(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly threads: readonly CaseThread[];
}): readonly ThreadVerdict[] {
  return options.threads.map((thread) => {
    const recorded = options.state.threads.find((candidate) => candidate.id === thread.id);
    const replies = (recorded?.comments ?? [])
      .filter((comment) => comment.author === options.state.viewer)
      .map((comment) => comment.body);
    const resolved = recorded?.resolved ?? false;

    if (recorded === undefined || !recorded.released) {
      return { id: thread.id, expected: thread.expected, passed: false, reason: "thread was never released to the agent" };
    }

    if (thread.expected === "decline") {
      const reason = replies.length > 0 ? "declined thread got a reply" : resolved ? "declined thread was resolved" : null;

      return { id: thread.id, expected: thread.expected, passed: reason === null, reason: reason ?? "ok" };
    }

    const reason = judgeFix({ workspace: options.workspace, state: options.state, thread, replies, resolved });

    return { id: thread.id, expected: thread.expected, passed: reason === null, reason: reason ?? "ok" };
  });
}
