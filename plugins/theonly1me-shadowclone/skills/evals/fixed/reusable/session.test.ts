import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, symlink, unlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fingerprint } from "../../shared/structured";
import { runStudySession } from "../../native/study/session";
import { engineRun } from "../../native/study/fixtures";
import { nativeSuite, selectedEnvironment } from "./bridge";
import { fixtureSuite } from "./testFixtures";
import { developmentCases } from "./definition";
import { parseReusableArguments } from "../../cli/reusableEval";
import { NativeInfrastructureError } from "../../native/diagnostics";
import type { Diagnostic } from "./schema";
import { protectedGuidanceFingerprint } from "../../native/study/protectedGuidance";

test("materialized told guidance follows the native skill path without oracle prompt injection", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-told-"));
  try {
    const entry = developmentCases[0];
    if (!entry) throw new Error("Expected public case.");
    const suite = fixtureSuite({ cases: [entry] });
    suite.templateDirectory = path.join(directory, "template");
    await mkdir(suite.templateDirectory, { mode: 0o700 });
    await Bun.write(path.join(suite.templateDirectory, "AGENTS.md"), "Use Bun.\n");
    const files = [
      {
        root: "home" as const,
        path: ".agents/skills/manual/SKILL.md",
        content: "Use clear names.\n",
        encoding: "utf8" as const,
        mode: 0o600,
      },
    ];
    suite.environments.codex.atlas.told = { files, fingerprint: fingerprint(files) };
    const guidance = selectedEnvironment({ suite, setup: "told", case: entry, repetition: 0 });
    let calls = 0;
    const record = await runStudySession({
      suite: nativeSuite({ suite, cases: [entry] }),
      task: entry.task,
      arm: "told",
      repeat: 0,
      guidance,
      outputDirectory: directory,
      deadlineAt: Date.now() + 30000,
      blockedPaths: ["/private/tmp/synthetic-answers"],
      budget: {
        reserve: async () => {
          calls += 1;
          return undefined;
        },
        settle: async () => {},
      },
      runner: async (options) => {
        expect(options.prompt).toBe(entry.task.turns[0] ?? "");
        expect(options.prompt).not.toContain("My standing preferences:");
        expect(options.memoryEnabled).toBe(true);
        expect(options.blockedPaths).toContain("/private/tmp/synthetic-answers");
        expect(
          await Bun.file(path.join(options.homeDirectory, ".agents/skills/manual/SKILL.md")).text(),
        ).toBe("Use clear names.\n");
        for (const file of entry.task.acceptance?.reference ?? [])
          await Bun.write(path.join(options.directory, file.path), file.content);
        return engineRun({ resolvedModel: "synthetic", cliVersion: "synthetic-cli" });
      },
    });
    expect(record.arm).toBe("told");
    expect(calls).toBe(1);
    expect(
      (
        await Array.fromAsync(
          new Bun.Glob("candidate-*").scan({ cwd: directory, onlyFiles: false }),
        )
      ).length,
    ).toBe(0);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("CLI authenticated phases require a new exact scope and explicit execution decision", () => {
  expect(() =>
    parseReusableArguments([
      "--protocol",
      "preference-respect-v3",
      "--phase",
      "run",
      "--suite-file",
      "/private/tmp/suite.json",
      "--yes",
    ]),
  ).toThrow();
  expect(() =>
    parseReusableArguments([
      "--protocol",
      "preference-respect-v3",
      "--phase",
      "learn",
      "--preparation-file",
      "/private/tmp/preparation.json",
      "--scope-file",
      "/private/tmp/scope.json",
    ]),
  ).toThrow();
  expect(
    parseReusableArguments([
      "--protocol",
      "preference-respect-v3",
      "--phase",
      "validate-sandbox",
      "--output-directory",
      "/private/tmp/probe",
    ])?.phase,
  ).toBe("validate-sandbox");
});

test("native transport remains private and inspectable after the disposable workspace is cleaned", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-native-transport-"));
  try {
    const entry = developmentCases[0];
    if (!entry) throw new Error("Expected public case.");
    const suite = fixtureSuite({ cases: [entry] });
    suite.templateDirectory = path.join(directory, "template");
    await mkdir(suite.templateDirectory);
    await Bun.write(path.join(suite.templateDirectory, "AGENTS.md"), "Use Bun.\n");
    await runStudySession({
      suite: nativeSuite({ suite, cases: [entry] }),
      task: entry.task,
      arm: "bare",
      repeat: 0,
      outputDirectory: directory,
      deadlineAt: Date.now() + 30000,
      onDiagnostic: async () => {},
      budget: { reserve: async () => undefined, settle: async () => {} },
      runner: async (options) => {
        await options.debugTransport?.({
          stdout: "Synthetic native transport.",
          stderr: "Synthetic stage diagnostic.",
        });
        for (const file of entry.task.acceptance?.reference ?? [])
          await Bun.write(path.join(options.directory, file.path), file.content);
        return engineRun({ resolvedModel: "synthetic", cliVersion: "synthetic-cli" });
      },
    });
    expect(await Bun.file(path.join(directory, "transport-0.json")).json()).toEqual({
      stdout: "Synthetic native transport.",
      stderr: "Synthetic stage diagnostic.",
    });
    expect(
      (
        await Array.fromAsync(
          new Bun.Glob("candidate-*").scan({ cwd: directory, onlyFiles: false }),
        )
      ).length,
    ).toBe(0);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("native infrastructure diagnostics retain charged attempts and replacements use fresh workspaces", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-native-attempts-"));
  try {
    const entry = developmentCases[0];
    if (!entry) throw new Error("Expected public case.");
    const suite = fixtureSuite({ cases: [entry] });
    suite.templateDirectory = path.join(directory, "template");
    await mkdir(suite.templateDirectory, { mode: 0o700 });
    await Bun.write(path.join(suite.templateDirectory, "AGENTS.md"), "Use Bun.\n");
    const workspaces: string[] = [];
    let reserved = 0;
    const diagnostics: Diagnostic[] = [];
    for (const attempt of [1, 2]) {
      const record = await runStudySession({
        suite: nativeSuite({ suite, cases: [entry] }),
        task: entry.task,
        arm: "bare",
        repeat: 0,
        outputDirectory: directory,
        deadlineAt: Date.now() + 30000,
        onDiagnostic: async (diagnostic) => {
          diagnostics.push(diagnostic);
        },
        budget: {
          reserve: async () => {
            reserved += 1;
            return undefined;
          },
          settle: async () => {},
        },
        runner: async (options) => {
          workspaces.push(options.directory);
          if (attempt === 1)
            throw new NativeInfrastructureError({
              stage: "execution",
              confirmedInfrastructure: true,
              message: "Synthetic startup failure.",
              details: "Fixture-only confirmed failure.",
            });
          for (const file of entry.task.acceptance?.reference ?? [])
            await Bun.write(path.join(options.directory, file.path), file.content);
          return engineRun({ resolvedModel: "synthetic", cliVersion: "synthetic-cli" });
        },
      });
      expect(record.status).toBe(attempt === 1 ? "error" : "complete");
    }
    expect(reserved).toBe(2);
    expect(workspaces[0]).not.toBe(workspaces[1]);
    expect(diagnostics[0]?.confirmedInfrastructure).toBe(true);
    expect(diagnostics[0]?.stage).toBe("execution");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("verification detects modifications to protected personal guidance", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-guidance-integrity-"));
  try {
    const entry = developmentCases[0];
    if (!entry) throw new Error("Expected public case.");
    const suite = fixtureSuite({ cases: [entry] });
    suite.templateDirectory = path.join(directory, "template");
    await mkdir(suite.templateDirectory, { mode: 0o700 });
    await Bun.write(path.join(suite.templateDirectory, "AGENTS.md"), "Use Bun.\n");
    const files = [
      {
        root: "home" as const,
        path: ".agents/skills/manual/SKILL.md",
        content: "Preserve this manual guidance.\n",
        encoding: "utf8" as const,
        mode: 0o600,
      },
    ];
    const record = await runStudySession({
      suite: nativeSuite({ suite, cases: [entry] }),
      task: entry.task,
      arm: "deep",
      repeat: 0,
      guidance: { files, fingerprint: fingerprint(files) },
      outputDirectory: directory,
      deadlineAt: Date.now() + 30000,
      onDiagnostic: async () => {},
      budget: { reserve: async () => undefined, settle: async () => {} },
      runner: async (options) => {
        await Bun.write(
          path.join(options.homeDirectory, ".agents/skills/manual/SKILL.md"),
          "Model changed the guidance.\n",
        );
        return engineRun({ resolvedModel: "synthetic", cliVersion: "synthetic-cli" });
      },
    });
    expect(record.safety).toBe("fail");
    expect(record.correctness).toBe("unknown");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("protected guidance hashes preserve bytes and detect substitution by a symlink", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-guidance-bytes-"));
  try {
    const file = path.join(directory, "SKILL.md");
    await Bun.write(file, new Uint8Array([255]));
    const original = await protectedGuidanceFingerprint([file]);
    await Bun.write(file, new Uint8Array([254]));
    expect(await protectedGuidanceFingerprint([file])).not.toBe(original);
    await Bun.write(file, new Uint8Array([255]));
    const target = path.join(directory, "replacement.md");
    await Bun.write(target, new Uint8Array([255]));
    await unlink(file);
    await symlink(target, file);
    expect(await protectedGuidanceFingerprint([file])).not.toBe(original);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
