import { mkdir } from "node:fs/promises";
import { copyWorkspace } from "../workspace";
import path from "node:path";
import { z } from "zod";
import { runNativeEngine, type NativeEngineRunner } from "@shadowclone/agents";
import { runProcess, ownedWrite } from "@shadowclone/core";
import { evaluationBudget } from "../../shared/accounting";
import { lockEvaluation } from "../../shared/lock";
import { fingerprint } from "../../shared/structured";
import { requirePrivateDirectory, treeFingerprint } from "../files";
import type { CoverageEntry } from "./coverage";
import { matrixReceiptSchema, runMatrix, type MatrixEntry, type MatrixReceipt } from "./matrix";
import { keyFileSchema } from "./phase";
import { preparationLayout, preparationSchema } from "./prepare";
import { studyReport } from "./report";
import { achievableReport, rescoreStudyReceipt } from "./views";
import { studyArms, studyEngines, studySuiteSchema, taskSchema, type PersonalArm, type StudySuite } from "./schema";
import { calibrateJudges, controlDecisions, controlEntries, freezeValidatedSuite, validateFixtures } from "./validate";

const readJson = async (filePath: string): Promise<unknown> => JSON.parse(await Bun.file(filePath).text());

async function productIdentity(): Promise<{ commit: string; tree: string }> {
  const git = async (arguments_: string[]) => (await runProcess({ arguments: ["git", ...arguments_], cwd: path.resolve(import.meta.dir, "../../.."),
    environment: { PATH: process.env.PATH }, maximumOutputBytes: 64_000_000 })).stdout;
  return { commit: (await git(["rev-parse", "HEAD"])).trim(), tree: fingerprint([await git(["diff", "HEAD"]), await git(["status", "--porcelain"])]) };
}

export async function assembleSuite(options: { preparationFile: string; keyFile: string; tasksFile: string }): Promise<string> {
  const preparation = preparationSchema.parse(await readJson(options.preparationFile));
  const key = keyFileSchema.parse(await readJson(options.keyFile));
  const layout = preparationLayout(await requirePrivateDirectory(preparation.studyDirectory));
  const product = await productIdentity();
  const suite = studySuiteSchema.parse({
    protocol: "preference-study-v1", version: 1, studyId: crypto.randomUUID(),
    productCommit: product.commit, productTreeFingerprint: product.tree,
    templateDirectory: preparation.templateDirectory, templateFingerprint: await treeFingerprint(preparation.templateDirectory),
    cliVersion: preparation.cliVersion, model: "gpt-6-sol", effort: "medium", ...key,
    arms: await readJson(layout.arms), memory: [], tasks: z.array(taskSchema).parse(await readJson(options.tasksFile)), droppedChecks: [],
    analysis: { repetitions: 3, bootstrapSeed: 20260928, bootstrapSamples: 10000 },
    limits: { maximumCalls: 260, concurrency: 8, codeTurnSeconds: 240, adviceTurnSeconds: 120, judgeSeconds: 60 },
  });
  const suiteFile = path.join(preparation.studyDirectory, "suite.draft.json");
  await ownedWrite({ path: suiteFile, content: JSON.stringify(suite, null, 2) });
  return suiteFile;
}

async function phaseContext(options: { suiteFile: string; outputDirectory: string; phase: "validation" | "scored"; calls?: number }) {
  const suite = studySuiteSchema.parse(await readJson(options.suiteFile));
  if (await treeFingerprint(suite.templateDirectory) !== suite.templateFingerprint) throw new Error("Study template changed after freeze");
  const directory = await requirePrivateDirectory(path.join(options.outputDirectory, options.phase));
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const receiptFile = path.join(directory, "receipt.json");
  const saved = await Bun.file(receiptFile).exists() ? matrixReceiptSchema.parse(await readJson(receiptFile)) : null;
  if (saved && saved.suiteFingerprint !== fingerprint(suite)) throw new Error("Resume requires the original suite");
  const budget = await evaluationBudget({ directory, resume: saved !== null, maximumCalls: options.calls ?? suite.limits.maximumCalls });
  const receipt: MatrixReceipt = saved ?? {
    protocol: "preference-study-v1", phase: options.phase, suiteFingerprint: fingerprint(suite),
    deadlineAt: Date.now() + 3 * 3_600_000, status: "running", runs: [], failure: null,
  };
  return { suite, directory, receiptFile, budget, receipt };
}

export async function validateStudy(options: { suiteFile: string; outputDirectory: string; reportOnly?: boolean; runner?: NativeEngineRunner }) {
  const context = await phaseContext({ ...options, phase: "validation", calls: 140 });
  const release = await lockEvaluation(context.directory);
  try {
    const fixtures = await validateFixtures({ suite: context.suite, outputDirectory: context.directory });
    if (!fixtures.passed) return { fixtures };
    const runner = options.runner ?? runNativeEngine;
    const calibrationFile = path.join(context.directory, "calibration.json");
    const calibration = await Bun.file(calibrationFile).exists()
      ? z.array(z.strictObject({ taskId: z.string(), checkId: z.string(), passed: z.boolean(), verdicts: z.array(z.string()) })).parse(await readJson(calibrationFile))
      : await calibrateJudges({ suite: context.suite, runner, budget: context.budget, outputDirectory: context.directory });
    await ownedWrite({ path: calibrationFile, content: JSON.stringify(calibration, null, 2) });
    const receipt = await runMatrix({ ...context, entries: controlEntries(context.suite), runner, outputDirectory: context.directory,
      concurrency: context.suite.limits.concurrency, writeLine: console.log });
    const dropped = controlDecisions({ suite: context.suite, receipt, calibration });
    const frozen = freezeValidatedSuite({ suite: context.suite, dropped });
    const frozenFile = options.suiteFile.replace(/\.json$/, ".frozen.json");
    if (options.reportOnly) {
      await ownedWrite({ path: path.join(context.directory, "controls.json"), content: JSON.stringify({ status: receipt.status, alreadyDefault: dropped }, null, 2) });
      return { status: receipt.status, failure: receipt.failure, reportOnly: true, alreadyDefault: dropped,
        checks: context.suite.tasks.flatMap((task) => task.checks.map((check) => `${task.id}/${check.id}`)) };
    }
    if (receipt.status === "complete") await ownedWrite({ path: frozenFile, content: JSON.stringify(frozen, null, 2) });
    const groups = new Set(frozen.tasks.flatMap((task) => task.checks.map((check) => frozen.keyItems.find((item) => item.id === check.keyItem)?.group)));
    return {
      fixtures, calibration, status: receipt.status, failure: receipt.failure, dropped,
      kept: frozen.tasks.map((task) => ({ task: task.id, checks: task.checks.map((check) => check.id) })),
      gate: { tasksWithTwoChecks: frozen.tasks.filter((task) => task.checks.length >= 2).length, groups: [...groups] },
      frozenFile: receipt.status === "complete" ? frozenFile : null, frozenFingerprint: fingerprint(frozen),
    };
  } finally {
    await release();
  }
}

export function scoredEntries(suite: StudySuite): MatrixEntry[] {
  return suite.tasks.flatMap((task, taskIndex) => Array.from({ length: suite.analysis.repetitions }, (_, repeat) =>
    studyArms.map((_, position) => ({ arm: studyArms[(taskIndex + repeat + position) % studyArms.length] ?? "bare", taskId: task.id, repeat })))).flat();
}

export async function runStudy(options: { suiteFile: string; outputDirectory: string; arms?: readonly string[]; tasks?: readonly string[]; concurrency?: number; runner?: NativeEngineRunner; writeLine?: (line: string) => void }) {
  const context = await phaseContext({ ...options, phase: "scored" });
  const release = await lockEvaluation(context.directory);
  try {
    const receipt = await runMatrix({ ...context, entries: scoredEntries(context.suite).filter((entry) => (!options.arms || options.arms.includes(entry.arm)) && (!options.tasks || options.tasks.includes(entry.taskId))), runner: options.runner ?? runNativeEngine,
      outputDirectory: context.directory, concurrency: options.concurrency ?? context.suite.limits.concurrency, writeLine: options.writeLine ?? console.log });
    return { status: receipt.status, failure: receipt.failure, runs: receipt.runs.length };
  } finally {
    await release();
  }
}

export async function reportStudy(options: {
  suiteFile: string; outputDirectory: string; coverageFile: string; baseReceiptFile?: string; candidateSuiteFile?: string;
}) {
  const suite = studySuiteSchema.parse(await readJson(options.suiteFile));
  const scored = matrixReceiptSchema.parse(await readJson(path.join(options.outputDirectory, "scored", "receipt.json")));
  const base = options.baseReceiptFile ? matrixReceiptSchema.parse(await readJson(options.baseReceiptFile)) : null;
  const replaced = new Set(scored.runs.map((run) => `${run.arm}/${run.taskId}`));
  const receipt = base ? { ...scored, runs: [...base.runs.filter((run) => !replaced.has(`${run.arm}/${run.taskId}`)), ...scored.runs] } : scored;
  const coverageJson = z.object({ coverage: z.record(z.string(), z.array(z.unknown())) }).parse(await readJson(options.coverageFile));
  const coverage: Partial<Record<PersonalArm, CoverageEntry[]>> = {};
  for (const arm of ["original", "first-time", "deep"] as const) {
    coverage[arm] = z.array(z.strictObject({ keyItem: z.string(), status: z.enum(["covered", "absent", "contradicted", "unknown"]),
      file: z.string().nullable(), route: z.enum(["always-read", "description-routed", "not-invocable", "none"]), quote: z.string().nullable() })).parse(coverageJson.coverage[arm] ?? []);
  }
  const report = studyReport({ suite, receipt: rescoreStudyReceipt({ suite, receipt }), coverage });
  const candidates = options.candidateSuiteFile ? studySuiteSchema.parse(await readJson(options.candidateSuiteFile)) : null;
  const combined = candidates ? { ...report, achievable: achievableReport({ candidates, frozen: suite, receipt, coverage }) } : report;
  await ownedWrite({ path: path.join(options.outputDirectory, "report.json"), content: JSON.stringify(combined, null, 2) });
  return combined;
}

async function cliVersion(engine: "codex" | "claude-code"): Promise<string> {
  const result = await runProcess({ arguments: [engine === "codex" ? "codex" : "claude", "--version"], cwd: process.cwd(),
    environment: { PATH: process.env.PATH }, timeoutMilliseconds: 30_000, maximumOutputBytes: 4096 });
  if (result.exitCode !== 0) throw new Error("Agent CLI version is unavailable");
  return result.stdout.trim();
}

export async function deriveSuite(options: {
  preparationFile: string; suiteFile: string; engine: "codex" | "claude-code"; model?: string; effort?: "medium" | "high";
}): Promise<string> {
  const preparation = preparationSchema.parse(await readJson(options.preparationFile));
  const base = studySuiteSchema.parse(await readJson(options.suiteFile));
  const directory = await requirePrivateDirectory(preparation.studyDirectory);
  const layout = preparationLayout(directory);
  const claude = options.engine === "claude-code";
  const templateDirectory = claude ? path.join(directory, "template-claude") : base.templateDirectory;

  if (claude && !await Bun.file(path.join(templateDirectory, "CLAUDE.md")).exists()) {
    await copyWorkspace({ source: base.templateDirectory, target: templateDirectory });
    await Bun.write(path.join(templateDirectory, "CLAUDE.md"), "@AGENTS.md\n");
  }

  const product = await productIdentity();
  const suite = studySuiteSchema.parse({
    ...base, studyId: crypto.randomUUID(), engine: options.engine, ...studyEngines[options.engine],
    ...(options.model ? { model: options.model } : {}), ...(options.effort ? { effort: options.effort } : {}),
    productCommit: product.commit, productTreeFingerprint: product.tree, cliVersion: await cliVersion(options.engine),
    templateDirectory, templateFingerprint: await treeFingerprint(templateDirectory),
    arms: await readJson(claude ? layout.armsClaude : layout.arms),
    limits: claude ? { ...base.limits, maximumCalls: 300, concurrency: 4, codeTurnSeconds: 360, adviceTurnSeconds: 180 } : base.limits,
  });
  const suiteFile = path.join(directory, `suite.${options.engine}${options.model ? `-${options.model}` : ""}.json`);
  await ownedWrite({ path: suiteFile, content: JSON.stringify(suite, null, 2) });
  return suiteFile;
}
