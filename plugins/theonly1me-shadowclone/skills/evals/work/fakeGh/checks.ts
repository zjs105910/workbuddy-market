import { cpSync, existsSync, mkdirSync, mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { runCommand, runGit } from "./git";
import { type CheckRun, type FakeState, takeId, type Workspace } from "./state";

const flakyOutput =
  "Error: connect ECONNRESET while downloading test fixtures from the artifact cache\nThe job was cancelled after a network error.";

function exportTree(options: {
  readonly workspace: Workspace;
  readonly sha: string;
  readonly directory: string;
}): void {
  rmSync(options.directory, { recursive: true, force: true });
  mkdirSync(options.directory, { recursive: true });

  const archive = `${options.directory}.tar`;

  runGit({
    cwd: options.workspace.remoteDirectory,
    args: ["archive", "--format=tar", `--output=${archive}`, options.sha],
  });
  runCommand({ command: ["tar", "-xf", archive, "-C", options.directory], cwd: options.workspace.root });
  rmSync(archive, { force: true });

  const hidden = path.join(options.workspace.stateDirectory, "ci");

  if (existsSync(hidden)) {
    cpSync(hidden, options.directory, { recursive: true });
  }
}

function executeJob(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly job: FakeState["jobs"][number];
  readonly sha: string;
  readonly attempt: number;
}): CheckRun {
  const id = takeId(options.state);
  const priorRuns = options.state.runs.filter((run) => run.job === options.job.name).length;

  if (priorRuns < options.job.flakyFailures) {
    return { id, job: options.job.name, sha: options.sha, attempt: options.attempt, conclusion: "failure", output: flakyOutput };
  }

  const directory = path.join(mkdtempSync(path.join(os.tmpdir(), "ci-")), "checkout");

  exportTree({ workspace: options.workspace, sha: options.sha, directory });

  const result = runCommand({ command: options.job.command, cwd: directory, timeoutMs: 90_000 });

  rmSync(path.dirname(directory), { recursive: true, force: true });

  return {
    id,
    job: options.job.name,
    sha: options.sha,
    attempt: options.attempt,
    conclusion: result.exitCode === 0 ? "success" : "failure",
    output: `${result.stdout}\n${result.stderr}`.trim().slice(-4000),
  };
}

export function latestRuns(options: {
  readonly state: FakeState;
  readonly sha: string;
}): readonly CheckRun[] {
  return options.state.jobs.flatMap((job) => {
    const runs = options.state.runs.filter((run) => run.sha === options.sha && run.job === job.name);
    const latest = runs.at(-1);

    return latest ? [latest] : [];
  });
}

export function ensureChecks(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly sha: string;
}): readonly CheckRun[] {
  for (const job of options.state.jobs) {
    const exists = options.state.runs.some((run) => run.sha === options.sha && run.job === job.name);

    if (!exists) {
      options.state.runs.push(
        executeJob({ workspace: options.workspace, state: options.state, job, sha: options.sha, attempt: 1 }),
      );
    }
  }

  return latestRuns({ state: options.state, sha: options.sha });
}

export function rerunJobs(options: {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly runId: number;
  readonly failedOnly: boolean;
}): readonly CheckRun[] {
  const anchor = options.state.runs.find((run) => run.id === options.runId);

  if (!anchor) {
    return [];
  }

  const targets = latestRuns({ state: options.state, sha: anchor.sha }).filter(
    (run) => !options.failedOnly || run.conclusion === "failure",
  );

  return targets.map((target) => {
    const job = options.state.jobs.find((candidate) => candidate.name === target.job);

    if (!job) {
      return target;
    }

    const rerun = executeJob({
      workspace: options.workspace,
      state: options.state,
      job,
      sha: anchor.sha,
      attempt: target.attempt + 1,
    });

    options.state.runs.push(rerun);

    return rerun;
  });
}

export function rollupConclusion(runs: readonly CheckRun[]): "success" | "failure" | "none" {
  if (runs.length === 0) {
    return "none";
  }

  return runs.every((run) => run.conclusion === "success") ? "success" : "failure";
}
