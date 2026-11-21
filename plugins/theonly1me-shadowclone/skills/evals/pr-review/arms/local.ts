import { writeFileSync } from "node:fs";
import path from "node:path";
import { runClaudeCode } from "@shadowclone/agents";
import { reviewBranch, reviewLocally, reviewMarkdown, type ReviewResult } from "@shadowclone/review";
import { branchRepositoryName } from "@shadowclone/review";
import { openqodexReview } from "./openqodex";
import type { ArmName, LocalArmName, LocalArmRunner } from "./types";

export const upstreamRepository = "vitejs/vite";

const shadowcloneLocal =
  (options: { readonly arm: ArmName; readonly clone: string; readonly model: string; readonly mode: "branch" | "upstream" }): LocalArmRunner =>
  async ({ entry, directory }) => {
    const startedAt = new Date().toISOString();
    const progress: string[] = [];
    const shared = {
      reviewModel: { runner: runClaudeCode, model: options.model, effort: null, network: true },
      runChecks: true,
      onProgress: (message: string) => progress.push(message),
    };
    const review = async (): Promise<ReviewResult> =>
      options.mode === "branch"
        ? reviewBranch({ ...shared, repository: await branchRepositoryName(entry.checkout), base: "main", checkout: entry.checkout })
        : reviewLocally({ ...shared, repository: upstreamRepository, number: entry.upstream, checkout: options.clone });

    try {
      const result = await review();

      writeFileSync(path.join(directory, "review.md"), reviewMarkdown(result));
      return { arm: options.arm, caseId: entry.id, number: entry.upstream, startedAt, finishedAt: new Date().toISOString(), status: "done", detail: progress.join(" | ").slice(0, 400), raw: result };
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);

      return { arm: options.arm, caseId: entry.id, number: entry.upstream, startedAt, finishedAt: null, status: "failed", detail: message.slice(0, 400), raw: null };
    }
  };

export function localRunner(options: { readonly arm: LocalArmName; readonly clone: string; readonly model: string }): LocalArmRunner {
  const { arm, clone, model } = options;

  if (arm === "shadowclone-branch" || arm === "shadowclone-upstream") {
    return shadowcloneLocal({ arm, clone, model, mode: arm === "shadowclone-branch" ? "branch" : "upstream" });
  }

  return ({ entry, directory }) =>
    arm === "openqodex-branch"
      ? openqodexReview({ arm, caseId: entry.id, number: entry.upstream, cwd: entry.checkout, target: ["--base", "main"], model, directory })
      : openqodexReview({ arm, caseId: entry.id, number: entry.upstream, cwd: clone, target: [`#${entry.upstream}`], model, directory });
}
