import type { PullFacts } from "../types";
import { parseDiff, type DiffFile } from "./diff";
import { readGit } from "./git";
import { readHistory } from "./history";
import { readStandards, type Standards } from "./standards";

export type { DiffFile } from "./diff";
export type { Standards } from "./standards";
export { branchRepositoryName, hasUncommittedChanges, readBranchFacts } from "./branch";
export { readPullFacts } from "./facts";

export type ReviewContext = {
  readonly facts: PullFacts;
  readonly mergeBaseSha: string;
  readonly files: readonly DiffFile[];
  readonly standards: Standards;
  readonly history: string;
};

async function assertCheckoutAtHead(options: {
  readonly checkout: string;
  readonly facts: PullFacts;
}): Promise<void> {
  const head = (
    await readGit({ checkout: options.checkout, arguments: ["rev-parse", "HEAD"] })
  ).trim();

  if (head !== options.facts.headSha) {
    throw new Error(
      `The checkout is at ${head.slice(0, 7)}, not the pull request head ${options.facts.headSha.slice(0, 7)}. Check out the head commit first.`,
    );
  }

  await readGit({
    checkout: options.checkout,
    arguments: ["cat-file", "-e", `${options.facts.baseSha}^{commit}`],
  }).catch(() => {
    throw new Error(
      `The checkout lacks the base commit ${options.facts.baseSha.slice(0, 7)}. Fetch the full history first.`,
    );
  });
}

export async function collectReview(options: {
  readonly checkout: string;
  readonly facts: PullFacts;
}): Promise<ReviewContext> {
  const { checkout, facts } = options;

  await assertCheckoutAtHead({ checkout, facts });

  const mergeBaseSha = (await readGit({ checkout, arguments: ["merge-base", facts.baseSha, facts.headSha] })).trim();

  const files = parseDiff(
    await readGit({
      checkout,
      arguments: [
        "diff",
        "--no-color",
        "--no-ext-diff",
        "--no-textconv",
        "--find-renames",
        "--unified=3",
        `${facts.baseSha}...${facts.headSha}`,
      ],
    }),
  );
  const standards = await readStandards({
    checkout,
    baseSha: facts.baseSha,
    changedPaths: files.map((file) => file.path),
  });
  const history = await readHistory({
    checkout,
    baseSha: facts.baseSha,
    paths: files.filter((file) => !file.deleted).map((file) => file.path),
  });

  return { facts, mergeBaseSha, files, standards, history };
}
