import { mkdir } from "node:fs/promises";
import path from "node:path";
import { readConfig, writeConfig, readManagedPolicy, projectPaths } from "@shadowclone/core";
import { learn } from "@shadowclone/cli";
import { readEnvironment } from "@shadowclone/environment";
import { readLearningState, readPendingLearning } from "@shadowclone/learning";
import { listSkillProposals } from "@shadowclone/skills";
import { evaluationBudget } from "../../shared/accounting";
import { lockEvaluation } from "../../shared/lock";
import { fingerprint } from "../../shared/structured";
import { requireExistingSkillPreserved } from "./environment";
import { workflowLearningRunner } from "./learner";
import { workflowLayout, captureWorkflowArm } from "./layout";
import { readWorkflowPreparation, requireWorkflowProduct, requirePreparationInputs, writeFrozenArtifact, readFrozenArtifact, requireWorkflowDefinition } from "./preparation";
import { preparedEnvironmentsSchema, type LearningCall } from "./schema";
import type { NativeEngineRunner } from "@shadowclone/agents";

export async function learnWorkflowEnvironments(options: { preparationFile: string; runner?: NativeEngineRunner; managedConfigPath?: string | null }) {
  const preparation = await readWorkflowPreparation(options.preparationFile);
  const directory = path.dirname(options.preparationFile);
  const layout = workflowLayout(directory);
  const managedConfigPath = options.managedConfigPath === undefined ? projectPaths.managedConfigFile : options.managedConfigPath;
  const policy = await readManagedPolicy(managedConfigPath);
  if (!policy.enabled || policy.distillation !== "allowed" || !policy.allowedEngines.includes(preparation.learner.engine) ||
    !policy.allowedSources.includes("claude-code") || !policy.allowedSources.includes("skill-library")) throw new Error("Managed policy does not permit synthetic learning preparation");
  await requireWorkflowProduct(preparation);
  const release = await lockEvaluation(directory);
  try {
    if (await Bun.file(path.join(layout.learning, "budget.json")).exists()) throw new Error("Learning was already attempted; retain its evidence and prepare a new directory");
    await requirePreparationInputs({ directory, preparation, beforeLearning: true });
    await mkdir(layout.learning, { mode: 0o700 });
    const budget = await evaluationBudget({ directory: layout.learning, resume: false, maximumCalls: preparation.learner.maximumCalls });
    const calls: LearningCall[] = [];
    const paths = layout.paths("deep");
    const config = await readConfig({ configPath: paths.configFile });
    await writeConfig({ configPath: paths.configFile, config: { ...config, sources: { ...config.sources, "claude-code": true }, distillation: { deep: true, automatic: false } } });
    let completed = true;
    try {
      await learn({ paths, workingDirectory: layout.workspace("deep"), managedConfigPath, deep: true, apply: true, confirm: () => true,
        engine: preparation.learner.engine, model: preparation.learner.model, reasoningEffort: preparation.learner.effort,
        maximumCalls: preparation.learner.maximumCalls, writeLine: () => {},
        runner: workflowLearningRunner({ directory: layout.learning, budget, configuration: preparation.learner, calls, runner: options.runner,
          blockedPaths: [directory, process.cwd()] }) });
    } catch {
      completed = false;
    }
    await requirePreparationInputs({ directory, preparation, beforeLearning: false });
    await requireWorkflowProduct(preparation);
    const environment = await readEnvironment(paths);
    const pendingRules = (await readPendingLearning(paths)).rules.length;
    const unresolvedRecords = environment?.records.filter(record => !environment.dispositions.some(entry => entry.key === record.rule.key && entry.status !== "pending")).length ?? 0;
    const unresolvedSkills = (await listSkillProposals(paths)).filter(proposal => proposal.status === "pending").length + unresolvedRecords;
    const processedEpisodes = (await readLearningState(paths)).processed.length;
    const capture = async (engine: "codex" | "claude-code") => {
      const original = preparation.starting[engine].original;
      const deep = await captureWorkflowArm({ directory, arm: "deep", engine });
      requireExistingSkillPreserved({ original, candidate: deep });
      return { ...preparation.starting[engine], deep };
    };
    const outcome = completed && calls.length > 0 && calls.every(call => !call.isError) && pendingRules === 0 && unresolvedSkills === 0 && processedEpisodes >= 2 ? "complete" : "incomplete";
    const prepared = preparedEnvironmentsSchema.parse({ protocol: "preference-respect-v2", preparation,
      preparationFingerprint: fingerprint(preparation), learning: { calls, outcome, processedEpisodes, pendingRules, unresolvedSkills,
        publishedRules: environment?.dispositions.filter(entry => entry.status === "published" || entry.status === "covered").length ?? 0 },
      engines: { codex: await capture("codex"), "claude-code": await capture("claude-code") } });
    await writeFrozenArtifact({ file: layout.environments, value: prepared });
    return { environmentsFile: layout.environments, learning: prepared.learning };
  } finally {
    await release();
  }
}

export async function readPreparedEnvironments(file: string) {
  const prepared = preparedEnvironmentsSchema.parse(await readFrozenArtifact(file));
  await requireWorkflowDefinition(prepared.preparation);
  if (prepared.preparationFingerprint !== fingerprint(prepared.preparation)) throw new Error("Learning preparation fingerprint changed");
  if (prepared.learning.outcome !== "complete" || prepared.learning.calls.length === 0 || prepared.learning.calls.length > prepared.preparation.learner.maximumCalls ||
    prepared.learning.calls.some(call => call.isError || call.model !== prepared.preparation.learner.model || call.cliVersion !== prepared.preparation.learner.cliVersion)) throw new Error("Learning preparation is incomplete or has unconfirmed model calls");
  if (prepared.learning.processedEpisodes < 2 || prepared.learning.pendingRules > 0 || prepared.learning.unresolvedSkills > 0) throw new Error("Learning preparation retains unresolved evidence");
  for (const engine of ["codex", "claude-code"] as const) {
    const environments = prepared.engines[engine];
    if (fingerprint({ original: environments.original, "first-time": environments["first-time"] }) !== fingerprint(prepared.preparation.starting[engine])) throw new Error("Starting guidance changed during learning");
    for (const arm of Object.values(environments)) if (arm.fingerprint !== fingerprint(arm.files)) throw new Error("Guidance fingerprint changed");
    requireExistingSkillPreserved({ original: environments.original, candidate: environments.deep });
  }
  return prepared;
}
