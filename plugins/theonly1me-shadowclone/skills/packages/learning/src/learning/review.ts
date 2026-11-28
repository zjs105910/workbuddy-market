import type { LearningExecution } from "@shadowclone/agents";
import type { ProjectPaths } from "@shadowclone/core";
import { readEffectiveConfig } from "@shadowclone/core";
import { persistLearningRules } from "./storage";
import { updatePendingLearning } from "./pending";
import { publishReviewedLearning } from "./publication";
import { writeLearningReceipt } from "./receipt";

export async function decidePendingLearning(options: {
  readonly paths: ProjectPaths;
  readonly key: string;
  readonly action: "apply" | "reject";
  readonly managedConfigPath?: string | null;
  readonly execution?: LearningExecution;
}): Promise<void> {
  await updatePendingLearning({
    paths: options.paths,
    update: async (state) => {
      const rule = state.rules.find((entry) => entry.key === options.key);
      if (!rule) throw new Error("Pending learned rule was not found");

      if (options.action === "apply") {
        const provenance = state.provenance[rule.key];
        const { config, policy } = await readEffectiveConfig({
          configPath: options.paths.configFile,
          managedConfigPath: options.managedConfigPath === undefined
            ? options.paths.managedConfigFile : options.managedConfigPath,
        });
        if (!config.distillation.deep || policy.distillation !== "allowed") {
          throw new Error("Enable learning consent before approving a learned rule");
        }
        if (!provenance?.complete || provenance.sources.length === 0) {
          throw new Error("Pending rule has unresolved source provenance. Learn again from enabled sources or reject it.");
        }
        const disabled = provenance.sources.filter((source) => !config.sources[source]);
        if (disabled.length > 0) {
          throw new Error(`Pending rule uses disabled sources: ${disabled.join(", ")}. It remains pending.`);
        }
        const receipt = {
          startedAt: Date.now(),
          mode: "manual" as const,
          episodeCount: 0,
          sourceCounts: Object.fromEntries(provenance.sources.map((source) => [source, 1])),
          proposalCount: 1,
          ruleKeys: [rule.key],
        };
        try {
          await persistLearningRules({ paths: options.paths, rules: [rule], provenance: { [rule.key]: provenance } });
          const publication = await publishReviewedLearning({ ...options, keys: [rule.key] });
          await writeLearningReceipt({
            paths: options.paths,
            receipt: {
              ...receipt,
              stage: "complete",
              outcome: publication.pending > 0 ? "needs-scope-or-publication" : "guidance-published",
              pendingCount: publication.pending,
              nextAction: publication.pending > 0
                ? "Run shadowclone learning pending to resolve publication."
                : "Start a new agent session to load active guidance.",
            },
          });
        } catch (error) {
          await writeLearningReceipt({
            paths: options.paths,
            receipt: {
              ...receipt,
              stage: "publication",
              outcome: "publication-failed",
              pendingCount: 1,
              nextAction: "The proposal remains pending. Check shadowclone doctor, then retry learning apply with its key.",
            },
          });
          throw error;
        }
      }
      return {
        ...state,
        rules: state.rules.filter((entry) => entry.key !== options.key),
        rejectedKeys: options.action === "reject"
          ? [...new Set([...state.rejectedKeys, options.key])]
          : state.rejectedKeys,
      };
    },
  });
}
