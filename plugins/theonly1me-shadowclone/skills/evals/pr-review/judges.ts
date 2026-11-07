import { z } from "zod";
import { runClaudeCode, runCodex } from "@shadowclone/agents";
import type { EngineRun } from "@shadowclone/agents";

export const judgeNames = ["opus", "sol"] as const;

export type JudgeName = (typeof judgeNames)[number];

export type JudgeAnswer<Output> = { readonly judge: JudgeName; readonly output: Output | null; readonly error: string | null };

function parsed<Output>(options: { readonly run: EngineRun; readonly schema: z.ZodType<Output> }): Output {
  return options.schema.parse(options.run.structured ?? JSON.parse(options.run.text));
}

async function ask<Output>(options: {
  readonly judge: JudgeName;
  readonly prompt: string;
  readonly schema: z.ZodType<Output>;
  readonly cwd: string;
}): Promise<JudgeAnswer<Output>> {
  const outputSchema = z.toJSONSchema(options.schema, { target: "draft-7" });

  try {
    const run =
      options.judge === "opus"
        ? await runClaudeCode({
            prompt: options.prompt,
            cwd: options.cwd,
            execution: { purpose: "review", network: false },
            allowedTools: ["Read", "Grep", "Glob"],
            permissionMode: "dontAsk",
            model: "claude-opus-5-5",
            reasoningEffort: "high",
            outputSchema,
          })
        : await runCodex({
            prompt: options.prompt,
            cwd: options.cwd,
            execution: { purpose: "evaluation", access: "read" },
            permissionMode: "dontAsk",
            model: "gpt-6.1-sol",
            reasoningEffort: "high",
            outputSchema,
          });

    if (run.isError) {
      return { judge: options.judge, output: null, error: (run.errorMessage ?? "the judge failed").slice(0, 300) };
    }

    return { judge: options.judge, output: parsed({ run, schema: options.schema }), error: null };
  } catch (error) {
    return { judge: options.judge, output: null, error: error instanceof Error ? error.message.slice(0, 300) : String(error) };
  }
}

export function askJudges<Output>(options: {
  readonly prompt: string;
  readonly schema: z.ZodType<Output>;
  readonly cwd: string;
}): Promise<readonly JudgeAnswer<Output>[]> {
  return Promise.all(judgeNames.map((judge) => ask({ ...options, judge })));
}
