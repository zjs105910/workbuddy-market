import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";

const releaseSchema = z.enum(["initial", "pr-created", "head-changed", "ready"]);

const reviewCommentSchema = z.strictObject({
  id: z.number(),
  author: z.string(),
  bot: z.boolean(),
  body: z.string(),
  createdAt: z.string(),
});

const threadSchema = z.strictObject({
  id: z.string(),
  pullRequest: z.number(),
  path: z.string(),
  line: z.number(),
  release: releaseSchema,
  released: z.boolean(),
  resolved: z.boolean(),
  resolvedBy: z.string().nullable(),
  comments: z.array(reviewCommentSchema),
});

const pullRequestSchema = z.strictObject({
  number: z.number(),
  title: z.string(),
  body: z.string(),
  head: z.string(),
  base: z.string(),
  draft: z.boolean(),
  approved: z.boolean(),
  state: z.enum(["OPEN", "CLOSED", "MERGED"]),
  initialHead: z.string().nullable(),
});

const jobSchema = z.strictObject({
  name: z.string(),
  command: z.array(z.string()).min(1),
  flakyFailures: z.number().int().min(0),
});

const runSchema = z.strictObject({
  id: z.number(),
  job: z.string(),
  sha: z.string(),
  attempt: z.number(),
  conclusion: z.enum(["success", "failure"]),
  output: z.string(),
});

const stackSchema = z.strictObject({
  trunk: z.string(),
  branches: z.array(z.string()).min(1),
  rebase: z
    .strictObject({
      index: z.number(),
      parentTips: z.record(z.string(), z.string()),
    })
    .nullable(),
});

export const stateSchema = z.strictObject({
  repository: z.strictObject({ owner: z.string(), name: z.string() }),
  defaultBranch: z.string(),
  viewer: z.string(),
  nextId: z.number(),
  nextPullRequest: z.number(),
  pullRequests: z.array(pullRequestSchema),
  threads: z.array(threadSchema),
  topLevelComments: z.array(
    z.strictObject({ pullRequest: z.number(), author: z.string(), body: z.string() }),
  ),
  jobs: z.array(jobSchema),
  runs: z.array(runSchema),
  stack: stackSchema.nullable(),
});

export type FakeState = z.infer<typeof stateSchema>;
export type PullRequest = FakeState["pullRequests"][number];
export type ReviewThread = FakeState["threads"][number];
export type CheckRun = FakeState["runs"][number];
export type Release = z.infer<typeof releaseSchema>;

export type Workspace = {
  readonly root: string;
  readonly stateDirectory: string;
  readonly remoteDirectory: string;
};

export function workspaceFor(root: string): Workspace {
  const stateDirectory = path.join(root, ".fake-gh");

  return {
    root,
    stateDirectory,
    remoteDirectory: path.join(stateDirectory, "remote.git"),
  };
}

export function readState(workspace: Workspace): FakeState {
  return stateSchema.parse(
    JSON.parse(readFileSync(path.join(workspace.stateDirectory, "state.json"), "utf8")),
  );
}

export function writeState(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
}): void {
  writeFileSync(
    path.join(options.workspace.stateDirectory, "state.json"),
    `${JSON.stringify(stateSchema.parse(options.state), null, 2)}\n`,
  );
}

export type LogEntry = {
  readonly argv: readonly string[];
  readonly operation: string;
  readonly supported: boolean;
  readonly exitCode: number;
  readonly details: Readonly<Record<string, unknown>>;
};

export function appendLog(options: {
  readonly workspace: Workspace;
  readonly entry: LogEntry;
}): void {
  appendFileSync(
    path.join(options.workspace.stateDirectory, "log.jsonl"),
    `${JSON.stringify({ at: new Date().toISOString(), ...options.entry })}\n`,
  );
}

export function takeId(state: FakeState): number {
  const id = state.nextId;

  state.nextId += 1;

  return id;
}
