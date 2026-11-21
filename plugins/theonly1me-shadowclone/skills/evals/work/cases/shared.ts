import type { CaseDefinition } from "../scaffold/definition";
import { baseFiles, standardJobs } from "../scaffold/project";

export const environmentNote =
  "\n\nThis environment has no network access. `gh` talks to a local stand-in for GitHub (`./bin/gh`) and accepts the usual commands, including `gh api` and `gh stack`.";

type Thread = CaseDefinition["threads"][number];
type Commit = CaseDefinition["local"][number]["commits"][number];

export function acceptance(body: string): Readonly<Record<string, string>> {
  return {
    "ci_acceptance/__init__.py": "",
    "ci_acceptance/test_acceptance.py": `import unittest\n\n${body.trim()}\n`,
  };
}

export function botThread(options: {
  readonly id: string;
  readonly pullRequest?: number;
  readonly path: string;
  readonly line: number;
  readonly author?: string;
  readonly body: string;
  readonly release?: Thread["release"];
  readonly expected: Thread["expected"];
}): Thread {
  return {
    id: options.id,
    pullRequest: options.pullRequest ?? 7,
    path: options.path,
    line: options.line,
    author: options.author ?? "review-bot[bot]",
    bot: true,
    body: options.body,
    release: options.release ?? "initial",
    expected: options.expected,
  };
}

export function humanThread(options: {
  readonly id: string;
  readonly path: string;
  readonly line: number;
  readonly body: string;
  readonly expected: Thread["expected"];
}): Thread {
  return {
    id: options.id,
    pullRequest: 7,
    path: options.path,
    line: options.line,
    author: "teammate",
    bot: false,
    body: options.body,
    release: "initial",
    expected: options.expected,
  };
}

export function pullRequestCase(options: {
  readonly id: string;
  readonly title: string;
  readonly tags: readonly string[];
  readonly prompt: string;
  readonly commits: readonly Commit[];
  readonly pullRequestTitle: string;
  readonly pullRequestBody: string;
  readonly threads: readonly Thread[];
  readonly hiddenTests: Readonly<Record<string, string>>;
  readonly scopePaths: readonly string[];
  readonly jobs?: CaseDefinition["jobs"];
  readonly upstream?: CaseDefinition["upstream"];
  readonly approved?: boolean;
  readonly policyJobs?: readonly string[];
}): CaseDefinition {
  return {
    id: options.id,
    title: options.title,
    split: "train",
    tags: [...options.tags],
    prompt: `${options.prompt}${environmentNote}`,
    files: baseFiles,
    local: [{ branch: "feature", from: "main", commits: [...options.commits] }],
    pushed: ["feature"],
    upstream: options.upstream ?? [],
    checkout: "feature",
    pullRequests: [
      {
        number: 7,
        title: options.pullRequestTitle,
        body: options.pullRequestBody,
        head: "feature",
        base: "main",
        draft: true,
        approved: options.approved ?? false,
      },
    ],
    stack: null,
    jobs: options.jobs ?? standardJobs,
    hiddenTests: options.hiddenTests,
    threads: [...options.threads],
    outcome: {
      readyPullRequests: [7],
      policyJobs: [...(options.policyJobs ?? [])],
      template: false,
      scopePaths: [...options.scopePaths],
    },
  };
}

export function templateBody(summary: string): string {
  return `## Summary\n\n${summary}\n\n## Testing\n\n- \`python3 -m unittest discover -s tests -t .\` passed.\n\n## Risk\n\nLow. The change is limited to the new code.\n`;
}
