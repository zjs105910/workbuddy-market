import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { NativeEngineOptions, NativeEngineRun } from "@shadowclone/agents";
import { fingerprint } from "../../shared/structured";
import type { StudySuite, StudyTask } from "./schema";

export const synthetic = "0".repeat(64);

export function studyTask(overrides: Partial<StudyTask> = {}): StudyTask {
  return {
    id: "rename-config", mode: "code", turns: ["rename cfg in the loader", "commit it"],
    git: { branches: [{ name: "chore/tal-502-loader-names", commits: [{ message: "chore: start loader cleanup", files: [
      { path: "src/loader.ts", content: "export const cfg = 1;\n", encoding: "utf8", mode: 0o600 },
    ] }] }], checkout: "chore/tal-502-loader-names", pushed: true },
    fixtures: [], acceptance: null,
    checks: [
      { id: "commit-shape", keyItem: "commit-subject-shape", kind: "commit-shape", afterTurn: 1, subjectOnly: true, subject: "^[a-z]+(\\([a-z0-9-]+\\))?: [a-z]", forbidden: ["tal-\\d+"] },
      { id: "no-comments", keyItem: "no-added-comments", kind: "no-added-comments" },
    ],
    ...overrides,
  };
}

export async function studyFixture(options: { tasks?: readonly StudyTask[] } = {}) {
  const root = await mkdtemp(path.join(os.tmpdir(), "study-fixture-"));
  const templateDirectory = path.join(root, "template");
  const outputDirectory = path.join(root, "output");
  await mkdir(outputDirectory, { recursive: true, mode: 0o700 });
  await Bun.write(path.join(templateDirectory, "AGENTS.md"), "Run bun test.\n");
  const armFiles = [{ root: "home" as const, path: ".agents/skills/names/SKILL.md", content: "---\nname: names\n---\nUse full words.\n", encoding: "utf8" as const, mode: 0o600 }];
  const arm = { files: armFiles, fingerprint: fingerprint(armFiles) };
  const suite: StudySuite = {
    protocol: "preference-study-v1", version: 1, studyId: crypto.randomUUID(), productCommit: "a".repeat(40),
    productTreeFingerprint: synthetic, templateDirectory, templateFingerprint: synthetic, cliVersion: "codex-cli 0.0.0",
    engine: "codex", model: "gpt-6-sol", effort: "medium",
    keyItems: ["commit-subject-shape", "no-added-comments", "concise-answers", "test-first"].map((id) => ({
      id, group: id === "test-first" ? "wizard" as const : "learned" as const, statement: `Synthetic preference ${id}.`, evidence: "synthetic",
    })),
    wizardBuild: ["testing-first"], resolutionRule: "Synthetic rule for fixtures only.",
    arms: { original: arm, "first-time": arm, deep: arm }, memory: [],
    tasks: [...(options.tasks ?? [studyTask()])], droppedChecks: [],
    analysis: { repetitions: 1, bootstrapSeed: 7, bootstrapSamples: 1000 },
    limits: { maximumCalls: 50, concurrency: 2, codeTurnSeconds: 60, adviceTurnSeconds: 60, judgeSeconds: 30 },
  };
  return { root, suite, outputDirectory, cleanup: () => rm(root, { recursive: true, force: true }) };
}

export function engineRun(overrides: Partial<NativeEngineRun> = {}): NativeEngineRun {
  return {
    engine: "codex", resolvedModel: "gpt-6-sol", sessionId: "session-1", transcriptPath: null, text: "", structured: null,
    costUsd: null, durationMs: 5, turns: 1, isError: false, permissionDenials: [], actions: [], errorMessage: null,
    cliVersion: "codex-cli 0.0.0", resumableSessionId: "session-1", usage: null, ...overrides,
  };
}

export async function runGit(options: { directory: string; arguments: readonly string[] }): Promise<void> {
  const child = Bun.spawn({ cmd: ["git", ...options.arguments], cwd: options.directory, stdout: "ignore", stderr: "ignore",
    env: { PATH: process.env.PATH, GIT_CONFIG_NOSYSTEM: "1", GIT_CONFIG_GLOBAL: "/dev/null" } });
  if (await child.exited !== 0) throw new Error("Synthetic git command failed");
}

export type RecordedCall = { readonly prompt: string; readonly resumeSessionId: string | undefined; readonly writablePaths: readonly string[] };

export function recordingRunner(options: { calls: RecordedCall[]; turn: (request: NativeEngineOptions, index: number) => Promise<NativeEngineRun> }) {
  return async (request: NativeEngineOptions) => {
    options.calls.push({ prompt: request.prompt, resumeSessionId: request.resumeSessionId, writablePaths: request.writablePaths ?? [] });
    return options.turn(request, options.calls.length - 1);
  };
}
