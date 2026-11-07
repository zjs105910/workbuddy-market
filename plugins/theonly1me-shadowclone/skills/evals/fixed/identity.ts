import path from "node:path";
import { snapshotWorkspace } from "./snapshot";
import { runProcess } from "@shadowclone/core";
import type { NativeEngine } from "@shadowclone/agents";
import { fingerprint } from "../shared/structured";
import ts from "typescript";

export const fixedRuntime = { bun: Bun.version, typescript: ts.version };

export async function fixedProductIdentity() {
  if (!await Bun.file(path.join(import.meta.dir, "fixtures/tasks.ts")).exists()) throw new Error("Fixed branch evaluations require the source runner from a Shadowclone checkout");
  const snapshot = await snapshotWorkspace({ cwd: path.resolve(import.meta.dir, "../..") });
  return { commit: snapshot.head, tree: snapshot.fingerprint, branch: snapshot.branch };
}

export async function fixedCliVersion(engine: NativeEngine): Promise<string> {
  const result = await runProcess({ arguments: [engine === "codex" ? "codex" : "claude", "--version"],
    cwd: process.cwd(), environment: { PATH: process.env.PATH }, timeoutMilliseconds: 30_000, maximumOutputBytes: 4096 });
  if (result.exitCode !== 0 || !result.stdout.trim()) throw new Error("Agent CLI version is unavailable");
  return result.stdout.trim();
}

export async function fixedGraderFingerprint(): Promise<string> {
  const directory = path.resolve(import.meta.dir, "..");
  const files = ["native/checks.ts", "native/study/report.ts", "fixed/report.ts"];
  for await (const relative of new Bun.Glob("native/study/checks/**/*.ts").scan({ cwd: directory })) {
    if (!relative.endsWith(".test.ts")) files.push(relative);
  }
  const contents = [];
  for (const filePath of files.sort()) contents.push([filePath, await Bun.file(path.join(directory, filePath)).text()]);
  return fingerprint(contents);
}
