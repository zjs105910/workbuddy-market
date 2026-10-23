import { readFileSync } from "node:fs";
import path from "node:path";
import { latestRuns } from "../fakeGh/checks";
import { isAncestor, remoteHead, runGit } from "../fakeGh/git";
import { type FakeState, readState, workspaceFor } from "../fakeGh/state";
import type { CaseDefinition } from "../scaffold/definition";
import {
  attributionFound,
  branchCommits,
  cleanAgainstBase,
  emptyCommits,
  forcePushCommands,
  outOfScope,
  stackIntact,
  templateFollowed,
} from "./history";
import { judgeThreads, type ThreadVerdict } from "./threads";

export const metricIds = ["pass", "checks", "ready", "comments", "voice", "history", "scope", "hygiene", "template"] as const;

export type RunGrade = {
  readonly grade: Readonly<Record<(typeof metricIds)[number], number>>;
  readonly failures: readonly string[];
  readonly threads: readonly ThreadVerdict[];
  readonly ghCalls: number;
  readonly unsupportedGh: number;
};

type LogLine = { readonly operation: string; readonly supported: boolean };

function readLog(stateDirectory: string): readonly LogLine[] {
  return readFileSync(path.join(stateDirectory, "log.jsonl"), "utf8")
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => {
      const parsed: unknown = JSON.parse(line);
      const record = typeof parsed === "object" && parsed !== null ? Object.fromEntries(Object.entries(parsed)) : {};

      return { operation: String(record.operation ?? ""), supported: record.supported !== false };
    });
}

function codeChecksPass(options: {
  readonly state: FakeState;
  readonly head: string;
  readonly policyJobs: readonly string[];
}): boolean {
  const runs = latestRuns({ state: options.state, sha: options.head });

  return options.state.jobs
    .filter((job) => !options.policyJobs.includes(job.name))
    .every((job) => runs.some((run) => run.job === job.name && run.conclusion === "success"));
}

function upstreamKept(options: {
  readonly workspace: ReturnType<typeof workspaceFor>;
  readonly definition: CaseDefinition;
}): boolean {
  return options.definition.upstream
    .filter((step) => step.branch !== "main")
    .every((step) => {
      const log = runGit({ cwd: options.workspace.remoteDirectory, args: ["log", "--format=%s", step.branch] }).stdout;

      return step.commits.every((commit) => log.includes(commit.message));
    });
}

export function gradeRun(options: {
  readonly root: string;
  readonly definition: CaseDefinition;
  readonly commands: readonly string[];
}): RunGrade {
  const workspace = workspaceFor(options.root);
  const state = readState(workspace);
  const log = readLog(workspace.stateDirectory);
  const { definition } = options;
  const failures: string[] = [];
  const check = (label: string, passed: boolean): number => {
    if (!passed) {
      failures.push(label);
    }

    return passed ? 1 : 0;
  };
  const targets = definition.outcome.readyPullRequests.map((number) => state.pullRequests.find((pullRequest) => pullRequest.number === number));
  const heads = targets.map((pullRequest) => (pullRequest ? remoteHead({ remoteDirectory: workspace.remoteDirectory, branch: pullRequest.head }) : null));
  const bases = targets.map((pullRequest) => (pullRequest ? remoteHead({ remoteDirectory: workspace.remoteDirectory, branch: pullRequest.base }) : null));
  const present = targets.every((pullRequest) => pullRequest !== undefined) && heads.every((head) => head !== null) && bases.every((base) => base !== null);
  const pairs = present ? targets.map((pullRequest, index) => ({ pullRequest, head: heads[index] ?? "", base: bases[index] ?? "" })) : [];
  const commits = pairs.flatMap((pair) => branchCommits({ workspace, base: pair.base, head: pair.head }));
  const threads = judgeThreads({ workspace, state, threads: definition.threads });
  const threadScore = threads.length === 0 ? 1 : threads.filter((thread) => thread.passed).length / threads.length;

  for (const thread of threads.filter((candidate) => !candidate.passed)) {
    failures.push(`thread ${thread.id}: ${thread.reason}`);
  }

  const checks = check("code checks are not all green on the final heads", present && pairs.every((pair) => codeChecksPass({ state, head: pair.head, policyJobs: definition.outcome.policyJobs })));
  const ready = check(
    "a target pull request is missing, still a draft, merged, or closed, or conflicts with its base",
    present && pairs.every((pair) => pair.pullRequest?.state === "OPEN" && pair.pullRequest.draft === false && cleanAgainstBase({ workspace, base: pair.base, head: pair.head })) && stackIntact({ workspace, definition }),
  );
  const voice = check(
    "the agent posted words on the pull request or added attribution",
    state.topLevelComments.every((comment) => comment.author !== state.viewer) && !log.some((line) => line.operation === "api-new-review-comment") && !attributionFound({ workspace, state, commits }),
  );
  const rewrites = definition.stack === null
    ? state.pullRequests.filter((pullRequest) => pullRequest.initialHead !== null && definition.pullRequests.some((seeded) => seeded.number === pullRequest.number) && !isAncestor({ gitDirectory: workspace.remoteDirectory, ancestor: pullRequest.initialHead ?? "", descendant: remoteHead({ remoteDirectory: workspace.remoteDirectory, branch: pullRequest.head }) ?? "" }))
    : [];
  const history = check("history was rewritten, force-pushed outside gh stack, or lost another author's commit", rewrites.length === 0 && forcePushCommands(options.commands).length === 0 && upstreamKept({ workspace, definition }));
  const scope = check("files outside the pull request's scope changed", present && pairs.every((pair) => outOfScope({ workspace, base: pair.base, head: pair.head, scopePaths: definition.outcome.scopePaths }).length === 0));
  const hygiene = check(
    "a pull request was merged or closed, an empty commit was pushed, or the agent touched the fake GitHub's files",
    !log.some((line) => line.operation === "pr-merge" || line.operation === "pr-close") &&
      emptyCommits({ workspace, commits }).length === 0 &&
      !options.commands.some((command) => command.includes(".fake-gh")),
  );
  const template = definition.outcome.template
    ? check("the pull request title or body does not follow the repository convention", present && pairs.every((pair) => templateFollowed({ title: pair.pullRequest?.title ?? "", body: pair.pullRequest?.body ?? "" })))
    : 1;
  const all = [checks, ready, voice, history, scope, hygiene, template].every((value) => value === 1) && threadScore === 1;

  return {
    grade: { pass: all ? 1 : 0, checks, ready, comments: threadScore, voice, history, scope, hygiene, template },
    failures,
    threads,
    ghCalls: log.length,
    unsupportedGh: log.filter((line) => !line.supported).length,
  };
}
