import path from "node:path";
import type { EngineRunner } from "@shadowclone/agents";
import { ownedWrite } from "@shadowclone/core";
import {
  distillationMergeOutputSchema,
  parseDistilledRules,
  parseMergeDrops,
  type DistilledRule,
} from "./schema";

export type DroppedRule = {
  readonly rule: DistilledRule;
  readonly reason: string;
};

export type MergedRules = {
  readonly rules: readonly DistilledRule[];
  readonly dropped: readonly DroppedRule[];
};

export function mergeCheckpointId(rules: readonly DistilledRule[]): string {
  const identity = rules.map((rule) => ({
    title: rule.title,
    body: rule.body,
    section: rule.section,
  }));

  return new Bun.CryptoHasher("sha256")
    .update(
      JSON.stringify({
        identity,
        outputSchema: distillationMergeOutputSchema,
        learnerVersion: "reconciliation-merge-v2",
      }),
    )
    .digest("hex")
    .slice(0, 24);
}

function resolveMerge(options: {
  readonly value: unknown;
  readonly inputs: readonly DistilledRule[];
}): MergedRules | null {
  const parsed = parseDistilledRules(options.value);
  const valid = parsed.every(
    (rule) =>
      rule.sources !== undefined &&
      rule.sources.length > 0 &&
      rule.sources.every((index) => index < options.inputs.length),
  );

  if (!valid) {
    return null;
  }

  const merged = new Set(parsed.flatMap((rule) => rule.sources ?? []));
  const dropped = new Map<number, DroppedRule>();

  for (const drop of parseMergeDrops(options.value)) {
    const rule = options.inputs[drop.index];

    if (rule && !merged.has(drop.index) && !dropped.has(drop.index)) {
      dropped.set(drop.index, { rule, reason: drop.reason });
    }
  }

  const kept = options.inputs.flatMap((rule, index) =>
    merged.has(index) || dropped.has(index) ? [] : [{ ...rule, sources: [index] }],
  );

  return { rules: [...parsed, ...kept], dropped: [...dropped.values()] };
}

function checkpointValue(options: {
  readonly merged: MergedRules;
  readonly inputs: readonly DistilledRule[];
}) {
  return {
    rules: options.merged.rules,
    dropped: options.merged.dropped.map((drop) => ({
      index: options.inputs.indexOf(drop.rule),
      reason: drop.reason,
    })),
  };
}

export async function mergeDistilledRules(options: {
  readonly rules: readonly DistilledRule[];
  readonly runner: EngineRunner;
  readonly cwd: string;
  readonly checkpointDirectory?: string;
}): Promise<MergedRules> {
  const unmerged: MergedRules = { rules: options.rules, dropped: [] };

  if (options.rules.length <= 1) {
    return unmerged;
  }

  const checkpointPath = options.checkpointDirectory
    ? path.join(
        options.checkpointDirectory,
        `merge-${mergeCheckpointId(options.rules)}.json`,
      )
    : null;

  if (checkpointPath && (await Bun.file(checkpointPath).exists())) {
    try {
      const cached: unknown = await Bun.file(checkpointPath).json();
      const parsed = resolveMerge({
        value: cached,
        inputs: options.rules,
      });

      if (parsed) {
        return parsed;
      }
    } catch {}
  }

  const prompt = [
    "You are an expert engineer. Below is a list of behavioral rules extracted from agent transcripts.",
    "Many of these rules are duplicates, restatements, or overlap significantly.",
    "Merge duplicates into one rule that keeps every condition and exception of the rules it replaces.",
    "For each consolidated rule, include a `sources` array with the 0-based integer indices of the input rules it consolidated.",
    "Drop a rule only when it is content-free telemetry, and list each dropped index in `dropped` with a one-sentence reason.",
    "Every input index must appear in exactly one rule's `sources` or in `dropped`.",
    "Output the consolidated set of rules as JSON matching the supplied schema.",
    "",
    ...options.rules.map(
      (rule, index) =>
        `[${index}] Title: ${rule.title}\nBody: ${rule.body}\nSection: ${rule.section}\n`,
    ),
  ].join("\n");

  const outputSchema = {
    ...distillationMergeOutputSchema,
    properties: {
      rules: {
        ...distillationMergeOutputSchema.properties.rules,
        maxItems: options.rules.length,
      },
    },
  };

  const run = await options.runner({
    prompt,
    cwd: options.cwd,
    execution: { purpose: "learning" },
    allowedTools: [],
    permissionMode: "dontAsk",
    outputSchema,
  });

  if (run.isError) {
    return unmerged;
  }

  let structured = run.structured;

  if (!structured) {
    try {
      structured = JSON.parse(run.text);
    } catch {
      return unmerged;
    }
  }

  try {
    const merged = resolveMerge({
      value: structured,
      inputs: options.rules,
    });

    if (!merged) {
      return unmerged;
    }

    if (checkpointPath) {
      await ownedWrite({
        path: checkpointPath,
        content: `${JSON.stringify(checkpointValue({ merged, inputs: options.rules }), null, 2)}\n`,
      });
    }

    return merged;
  } catch {
    return unmerged;
  }
}
