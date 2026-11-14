import path from "node:path";
import { z } from "zod";
import { reviewNetworkTools, reviewTools } from "@shadowclone/agents";
import type { EngineRunner, ReasoningEffort } from "@shadowclone/agents";
import { redactSecrets } from "@shadowclone/redact";
import { type Analysis, analysisSchema } from "./types";
import { seedSkillsDirectory } from "@shadowclone/core";

export const defaultCodexReviewModel = "gpt-6.1-sol";

export type ReviewModel = {
  readonly runner: EngineRunner;
  readonly engine?: "claude" | "codex";
  readonly model: string;
  readonly effort: ReasoningEffort | null;
  readonly network: boolean;
};

export type AnalysisRun = {
  readonly output: Analysis;
  readonly costUsd: number | null;
};

export async function readReviewSkill(): Promise<string> {
  const text = await Bun.file(path.join(await seedSkillsDirectory(), "shadowclone-review", "SKILL.md")).text();
  const body = /^---\n[\s\S]*?\n---\n([\s\S]*)$/.exec(text)?.[1];

  if (body === undefined) {
    throw new Error("The bundled shadowclone-review skill is missing its frontmatter");
  }

  return body.trim();
}

export async function analyzeReview(options: {
  readonly reviewModel: ReviewModel;
  readonly checkout: string;
  readonly prompt: string;
}): Promise<AnalysisRun> {
  const run = await options.reviewModel.runner({
    prompt: options.prompt,
    cwd: options.checkout,
    execution: { purpose: "review", network: options.reviewModel.network },
    ...(options.reviewModel.engine === "codex"
      ? {}
      : { allowedTools: options.reviewModel.network ? [...reviewTools, ...reviewNetworkTools] : reviewTools }),
    permissionMode: "dontAsk",
    model: options.reviewModel.model,
    ...(options.reviewModel.effort === null ? {} : { reasoningEffort: options.reviewModel.effort }),
    outputSchema: z.toJSONSchema(analysisSchema, { target: "draft-7" }),
  });

  if (run.isError) {
    const reason = redactSecrets({ text: run.errorMessage ?? "No diagnostic was returned." });

    throw new Error(`The review run failed: ${reason.slice(0, 600)}`);
  }

  return {
    output: analysisSchema.parse(run.structured ?? JSON.parse(run.text)),
    costUsd: run.costUsd,
  };
}
