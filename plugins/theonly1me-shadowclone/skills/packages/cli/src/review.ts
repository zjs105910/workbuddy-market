import path from "node:path";
import { runClaudeCode } from "@shadowclone/agents";
import { runHostCommand, projectPaths, ownedWrite } from "@shadowclone/core";
import { reviewBranch, reviewLocally, reviewMarkdown, type ReviewResult } from "@shadowclone/review";
import { branchRepositoryName } from "@shadowclone/review";
import { parseReviewArguments } from "./reviewArguments";
import { requestCloudReview } from "./reviewCloud";
import { reviewStages } from "./reviewStages";

async function commandOutput(options: { readonly arguments: readonly string[]; readonly cwd: string; readonly failure: string }): Promise<string> {
  const result = await runHostCommand({ arguments: options.arguments, cwd: options.cwd });

  if (result.exitCode !== 0) {
    throw new Error(`${options.failure}: ${result.stderr.trim().slice(0, 300)}`);
  }

  return result.stdout.trim();
}

async function writeReview(options: { readonly result: ReviewResult; readonly output: string | null; readonly fileName: string }): Promise<void> {
  const { result } = options;
  const output = path.resolve(
    options.output ?? path.join(projectPaths.shadowcloneDirectory, "reviews", result.pull.repository.replace("/", "-"), options.fileName),
  );

  await ownedWrite({ path: output, content: reviewMarkdown(result) });
  console.log(`${result.findings.length} ${result.findings.length === 1 ? "finding" : "findings"}. Review written to ${output}`);
}

export async function reviewCommand(arguments_: readonly string[]): Promise<void> {
  const [first = "", ...rest] = arguments_;
  const stage = reviewStages[first];

  if (stage !== undefined) {
    await stage(rest);
    return;
  }

  const parsed = parseReviewArguments(arguments_);
  const cwd = process.cwd();
  const checkout = await commandOutput({
    arguments: ["git", "rev-parse", "--show-toplevel"],
    cwd,
    failure: "Run shadowclone review inside a Git repository",
  });
  const reviewModel = { runner: runClaudeCode, model: parsed.model, effort: parsed.effort, network: parsed.network };
  const onProgress = (message: string) => console.error(message);
  const { target } = parsed;

  if (target.kind === "branch") {
    const repository = parsed.repository ?? (await branchRepositoryName(checkout));
    const result = await reviewBranch({ repository, base: target.base, checkout, reviewModel, runChecks: parsed.runChecks, onProgress });

    await writeReview({ result, output: parsed.output, fileName: `branch-${result.pull.headSha.slice(0, 7)}.md` });
    return;
  }

  const repository =
    parsed.repository ??
    (await commandOutput({
      arguments: ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
      cwd: checkout,
      failure: "gh could not find the GitHub repository for this checkout",
    }));

  if (parsed.cloud) {
    await requestCloudReview({ repository, number: target.number });
    return;
  }

  const result = await reviewLocally({ repository, number: target.number, checkout, reviewModel, runChecks: parsed.runChecks, onProgress });

  await writeReview({ result, output: parsed.output, fileName: `pr-${target.number}-${result.pull.headSha.slice(0, 7)}.md` });
}
