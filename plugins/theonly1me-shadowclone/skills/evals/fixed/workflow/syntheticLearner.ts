import { z } from "zod";
import type { NativeEngineRunner } from "@shadowclone/agents";
import { corrections } from "./fixtures";

const learningSchema = z.object({ learnings: z.array(z.object({ key: z.string(), text: z.string() })) });

export function syntheticLearner(options: { prompts: string[] }): NativeEngineRunner {
  return async run => {
    options.prompts.push(run.prompt);
    let structured: unknown;
    if (run.prompt.includes("Organize durable user learning")) {
      const data = learningSchema.parse(JSON.parse(run.prompt.split("\n\n").at(-1) ?? "null"));
      structured = { routes: data.learnings.map(({ key }) => ({ key, destination: "baseline", skillId: "", name: "shadowclone-baseline",
        description: "Personal working defaults", reason: "Explicit global correction" })) };
    } else if (run.prompt.includes("Maintain one portable skill")) {
      const data = learningSchema.parse(JSON.parse(run.prompt.split("\n\n").at(-1) ?? "null"));
      structured = { body: "", description: "", edits: [{ before: "", after: data.learnings.map(learning => learning.text).join("\n\n"), keys: data.learnings.map(learning => learning.key) }],
        outcomes: data.learnings.map(learning => ({ key: learning.key, disposition: "apply", reason: "Preserves the explicit correction" })) };
    } else if (run.prompt.includes("Merge duplicates into one rule")) {
      structured = { rules: [...run.prompt.matchAll(/\[(\d+)\] Title: ([^\n]+)\nBody: ([^\n]+)\nSection: ([^\n]+)/g)].map(match => ({
        title: match[2], body: match[3], section: match[4], sources: [Number(match[1])],
      })), dropped: [] };
    } else if (run.prompt.includes("Reconcile correction evidence")) {
      const evidence = run.prompt.split("Correction evidence\n").at(-1) ?? "";
      const blocks = evidence.split(/(?=evidence-\d+ \[)/);
      const rules = corrections.flatMap(session => {
        const correction = session.messages.at(-1)?.text;
        if (!correction) throw new Error("Synthetic correction is missing");
        const block = blocks.find(text => text.includes(correction));
        const token = block?.match(/^evidence-\d+/)?.[0];
        return token ? [{ title: session.sessionId, body: correction, section: "workflow", observed: "Explicit personal correction", evidenceTokens: [token], rejectionToken: "" }] : [];
      });
      structured = { existingRules: [], newRules: rules, assessments: rules.flatMap(rule => rule.evidenceTokens.map(evidenceToken => ({
        evidenceToken, intent: "preference", durable: true, explicit: true, scope: "global",
      }))) };
    } else if (run.prompt.includes("Review skill catalog overlap")) structured = { overlaps: [] };
    else throw new Error("Unexpected synthetic learning prompt");
    return { engine: run.engine, resolvedModel: run.model, sessionId: "synthetic", transcriptPath: null, text: "", structured,
      costUsd: 0, durationMs: 1, turns: 1, isError: false, permissionDenials: [], actions: [], errorMessage: null,
      cliVersion: "synthetic-cli", resumableSessionId: null, usage: null };
  };
}
