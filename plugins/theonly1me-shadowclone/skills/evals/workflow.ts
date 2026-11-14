import path from "node:path";
import { z } from "zod";
import { ownedWrite, readLocalText } from "@shadowclone/core";
import { requirePrivateDirectory } from "./native/files";
import { fingerprint } from "./shared/structured";
import { lockEvaluation } from "./shared/lock";
import { workflowOutcomeSchema, summarizeOutcomes } from "./shared/outcome";

export const workflowConditions = [
  "existing-skills",
  "current-shadowclone",
  "evolved-workflow",
] as const;
const tasksSchema = z
  .array(
    z.strictObject({
      id: z.string().regex(/^[a-z0-9-]+$/),
      prompt: z.string().min(1).max(16_000),
      acceptance: z.array(z.string().min(1).max(2000)).min(1).max(32),
    }),
  )
  .min(1)
  .max(100);
const suiteSchema = z.strictObject({
  protocol: z.literal("workflow-outcomes-v1"),
  frozenAt: z.iso.datetime(),
  fingerprint: z.string(),
  tasks: tasksSchema,
});
export const workflowResultSchema = z.strictObject({
  suiteFingerprint: z.string(),
  taskId: z.string(),
  repeat: z.number().int().min(0),
  condition: z.enum(workflowConditions),
  host: z.enum(["claude-code", "codex"]),
  hostVersion: z.string().min(1),
  model: z.string().min(1),
  budgetUsd: z.number().positive(),
  productRevision: z.string().min(1),
  startedAt: z.iso.datetime(),
  outcome: workflowOutcomeSchema,
});

async function privateJson(filePath: string): Promise<unknown> {
  const directory = await requirePrivateDirectory(path.dirname(filePath));
  const text = await readLocalText(
    path.join(directory, path.basename(filePath)),
  );
  if (text === null) throw new Error("Private evaluation input was not found");
  return JSON.parse(text);
}

export async function freezeWorkflowTasks(options: {
  readonly tasksFile: string;
  readonly outputDirectory: string;
}) {
  const tasks = tasksSchema.parse(await privateJson(options.tasksFile));
  if (new Set(tasks.map((task) => task.id)).size !== tasks.length)
    throw new Error("Frozen task IDs must be unique");
  const directory = await requirePrivateDirectory(options.outputDirectory);
  const release = await lockEvaluation(directory);
  try {
    const filePath = path.join(directory, "workflow-suite.json");
    if (await Bun.file(filePath).exists())
      throw new Error(
        "A frozen workflow suite already exists; use a new study directory",
      );
    const suite = suiteSchema.parse({
      protocol: "workflow-outcomes-v1",
      frozenAt: new Date().toISOString(),
      fingerprint: fingerprint(tasks),
      tasks,
    });
    await ownedWrite({
      path: filePath,
      content: `${JSON.stringify(suite, null, 2)}\n`,
    });
    return { filePath, fingerprint: suite.fingerprint, tasks: tasks.length };
  } finally {
    await release();
  }
}

export async function reportWorkflowOutcomes(options: {
  readonly suiteFile: string;
  readonly resultsFile: string;
}) {
  const suite = suiteSchema.parse(await privateJson(options.suiteFile));
  if (suite.fingerprint !== fingerprint(suite.tasks))
    throw new Error("Frozen task definitions changed");
  const results = z
    .array(workflowResultSchema)
    .max(3000)
    .parse(await privateJson(options.resultsFile));
  const tasks = new Set(suite.tasks.map((task) => task.id));
  for (const result of results) {
    if (
      result.suiteFingerprint !== suite.fingerprint ||
      !tasks.has(result.taskId) ||
      Date.parse(result.startedAt) < Date.parse(suite.frozenAt)
    )
      throw new Error(
        "Results must refer to tasks frozen before their execution",
      );
  }
  const groups = Map.groupBy(results, (result) =>
    JSON.stringify([
      result.taskId,
      result.repeat,
      result.host,
      result.hostVersion,
      result.model,
      result.budgetUsd,
    ]),
  );
  for (const group of groups.values()) {
    if (new Set(group.map((result) => result.condition)).size !== group.length)
      throw new Error("Duplicate workflow condition in a matched comparison");
  }
  const matched = [...groups.values()].filter((group) =>
    workflowConditions.every((condition) =>
      group.some((result) => result.condition === condition),
    ),
  );
  const report = {
    protocol: suite.protocol,
    fingerprint: suite.fingerprint,
    matchedGroups: matched.length,
    unmatchedGroups: groups.size - matched.length,
    missingTasks: suite.tasks
      .filter((task) => !results.some((result) => result.taskId === task.id))
      .map((task) => task.id),
    conditions: workflowConditions.map((condition) => ({
      condition,
      ...summarizeOutcomes(
        matched.flatMap((group) =>
          group
            .filter((result) => result.condition === condition)
            .map((result) => result.outcome),
        ),
      ),
    })),
    limitation:
      "Descriptive matched outcomes only. These reports do not establish causal improvement, host qualification, or population-wide throughput.",
  };
  await ownedWrite({
    path: path.join(path.dirname(options.suiteFile), "workflow-report.json"),
    content: `${JSON.stringify(report, null, 2)}\n`,
  });
  return report;
}
