import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { runProcess } from "@shadowclone/core";
import type { ReviewModel } from "./analyze";
import { hasUncommittedChanges, readBranchFacts, readPullFacts } from "./collect";
import { analyzeStage, checksStage, preparePacket } from "./stages";
import type { PullFacts, ReviewResult } from "./types";
import { addWorktree, removeWorktree } from "./worktree";

async function fetchPullRefs(options: { readonly checkout: string; readonly number: number; readonly baseRefName: string }): Promise<void> {
  const fetched = await runProcess({
    arguments: ["git", "fetch", "--no-tags", "origin", `refs/pull/${options.number}/head`, `refs/heads/${options.baseRefName}`],
    cwd: options.checkout,
    environment: process.env,
    timeoutMilliseconds: 300_000,
  });

  if (fetched.exitCode !== 0) {
    throw new Error(`git could not fetch pull request ${options.number}: ${fetched.stderr.trim().slice(0, 300)}`);
  }
}

type LocalReviewOptions = {
  readonly checkout: string;
  readonly reviewModel: ReviewModel;
  readonly runChecks: boolean;
  readonly onProgress: (message: string) => void;
};

async function reviewAtHead(options: LocalReviewOptions & { readonly facts: PullFacts }): Promise<ReviewResult> {
  const { checkout, facts, onProgress } = options;
  const workDirectory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-review-"));
  const headDirectory = path.join(workDirectory, "head");

  try {
    const head = await addWorktree({ repository: checkout, sha: facts.headSha, directory: headDirectory });
    const packet = await preparePacket({ facts, checkout: head.root, network: options.reviewModel.network });

    onProgress(`Built-in rules matched ${packet.ruleHits.length} added lines`);

    const checks = options.runChecks ? await checksStage({ packet, repository: checkout, workDirectory, onProgress }) : null;

    onProgress(`Reviewing with ${options.reviewModel.model}`);

    return await analyzeStage({ packet, checks, checkout: head.root, reviewModel: options.reviewModel });
  } finally {
    await removeWorktree({ repository: checkout, directory: headDirectory });
    await rm(workDirectory, { recursive: true, force: true });
  }
}

export async function reviewLocally(options: LocalReviewOptions & { readonly repository: string; readonly number: number }): Promise<ReviewResult> {
  const facts = await readPullFacts({ repository: options.repository, number: options.number, cwd: options.checkout });

  options.onProgress(`Fetching pull request ${options.number}`);
  await fetchPullRefs({ checkout: options.checkout, number: options.number, baseRefName: facts.baseRefName });

  return reviewAtHead({ ...options, facts });
}

export async function reviewBranch(options: LocalReviewOptions & { readonly repository: string; readonly base: string | null }): Promise<ReviewResult> {
  const facts = await readBranchFacts({ checkout: options.checkout, repository: options.repository, base: options.base });

  options.onProgress(`Reviewing ${facts.headSha.slice(0, 7)} from the point where it left ${facts.baseRefName}`);

  if (await hasUncommittedChanges(options.checkout)) {
    options.onProgress("Uncommitted changes are not part of this review. Commit them to include them.");
  }

  return reviewAtHead({ ...options, facts });
}
