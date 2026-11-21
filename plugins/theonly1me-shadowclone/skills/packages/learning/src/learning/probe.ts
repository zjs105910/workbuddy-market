import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import { runNativeEngine, type NativeEngine, type NativeEngineRunner } from "@shadowclone/agents";
import { fingerprint, readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import { freezeProbeGuidance } from "./probeSnapshot";

const probeReceiptSchema = z.strictObject({
  id: z.uuid(),
  key: z.string(),
  engine: z.enum(["claude-code", "codex"]),
  inputFingerprint: z.string(),
  guidanceHash: z.string(),
  taskHash: z.string(),
  expectedHash: z.string(),
  startedAt: z.number(),
  completedAt: z.number(),
  outcome: z.enum(["pass", "fail", "error"]),
  delivery: z.literal("frozen-native-guidance"),
  hooksTested: z.literal(false),
  skillReadObserved: z.boolean(),
  permissionDenials: z.number(),
  model: z.string().nullable(),
  cliVersion: z.string().nullable(),
  nextAction: z.string(),
});

export async function readLatestProbe(paths: ProjectPaths) {
  const text = await readLocalText(path.join(paths.shadowcloneDirectory, "learning-probes", "latest.json"));
  return text === null ? null : probeReceiptSchema.parse(JSON.parse(text));
}

export async function runLearningProbe(options: {
  readonly paths: ProjectPaths;
  readonly key: string;
  readonly engine: NativeEngine;
  readonly cwd: string;
  readonly task: string;
  readonly expected: string;
  readonly approved: boolean;
  readonly runner?: NativeEngineRunner;
  readonly model?: string;
}) {
  if (!options.approved) throw new Error("Add --yes to authorize one paid agent call with redacted installed guidance and your synthetic task");
  if (!options.task.trim() || !options.expected.trim() || Buffer.byteLength(options.task) > 8_192 ||
    Buffer.byteLength(options.expected) > 4_096) throw new Error("A probe needs a short task and exact expected response");
  if (!options.runner && process.platform !== "darwin") throw new Error("The isolated native probe currently requires macOS");
  const snapshot = await freezeProbeGuidance(options);
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-probe-"));
  const homeDirectory = path.join(root, "home");
  const directory = path.join(root, "workspace");
  const startedAt = Date.now();
  let outcome: "pass" | "fail" | "error" = "error";
  let model: string | null = null;
  let cliVersion: string | null = null;
  let permissionDenials = 0;
  let skillReadObserved = false;
  try {
    await mkdir(homeDirectory, { recursive: true, mode: 0o700 });
    await mkdir(directory, { recursive: true, mode: 0o700 });
    for (const file of snapshot.files) {
      await Bun.write(path.join(file.location === "home" ? homeDirectory : directory, file.relativePath), file.text, { mode: 0o600 });
    }
    const run = await (options.runner ?? runNativeEngine)({
      engine: options.engine, prompt: redactSecrets({ text: options.task }),
      directory, homeDirectory, memoryEnabled: false, access: "read",
      blockedPaths: [options.cwd, options.paths.shadowcloneDirectory], protectedPaths: [],
      persistSession: false, signal: AbortSignal.timeout(60_000), model: options.model,
    });
    model = run.resolvedModel ?? null;
    cliVersion = run.cliVersion;
    permissionDenials = run.permissionDenials.length;
    skillReadObserved = run.actions.some((action) => action.succeeded === true &&
      (action.tool === "Skill" || action.path?.endsWith("/SKILL.md") === true));
    outcome = run.isError ? "error" : run.text.trim() === redactSecrets({ text: options.expected }).trim() ? "pass" : "fail";
  } catch {
    outcome = "error";
  } finally {
    await rm(root, { recursive: true, force: true });
  }
  const receipt = probeReceiptSchema.parse({
    id: crypto.randomUUID(), key: options.key, engine: options.engine,
    inputFingerprint: snapshot.inputFingerprint,
    guidanceHash: fingerprint(JSON.stringify(snapshot.files)),
    taskHash: fingerprint(options.task), expectedHash: fingerprint(options.expected),
    startedAt, completedAt: Date.now(), outcome,
    delivery: "frozen-native-guidance", hooksTested: false,
    skillReadObserved, permissionDenials, model, cliVersion,
    nextAction: outcome === "pass" ? "This response matched the probe. Future behavior still needs observation."
      : outcome === "fail" ? "Review the rule, scope, and task. The response did not match the exact expected text."
        : "Check shadowclone doctor and agent authentication before retrying.",
  });
  const text = `${JSON.stringify(receipt, null, 2)}\n`;
  const filePath = path.join(options.paths.shadowcloneDirectory, "learning-probes", `${receipt.id}.json`);
  await replaceLocalText({ filePath, previous: null, next: text });
  const latest = path.join(options.paths.shadowcloneDirectory, "learning-probes", "latest.json");
  await replaceLocalText({ filePath: latest, previous: await readLocalText(latest), next: text });
  return receipt;
}
