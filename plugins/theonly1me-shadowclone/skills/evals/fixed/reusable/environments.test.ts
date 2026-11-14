import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  prepareManualEnvironment,
  captureEnvironment,
  requireManualPreserved,
  reusableLayout,
  materializeCorpus,
} from "./environments";
import { existingManualSkill, intendedAtlasSkill } from "./guidance";
import { readHeldout, approveCaseReview } from "./seal";
import { writeFrozenArtifact } from "../workflow/preparation";
import { fixtureCases } from "./testFixtures";

test("offline routed and told environments preserve manual bytes and repository scope", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-environment-"));
  try {
    for (const arm of ["skills", "routing", "told"])
      await prepareManualEnvironment({
        directory,
        arm,
        routed: arm !== "skills",
        told: arm === "told",
      });
    for (const engine of ["codex", "claude-code"] as const) {
      const original = await captureEnvironment({
        directory,
        arm: "skills",
        repository: "atlas",
        engine,
      });
      const routing = await captureEnvironment({
        directory,
        arm: "routing",
        repository: "atlas",
        engine,
      });
      const told = await captureEnvironment({
        directory,
        arm: "told",
        repository: "atlas",
        engine,
      });
      const unrelated = await captureEnvironment({
        directory,
        arm: "told",
        repository: "boreal",
        engine,
      });
      requireManualPreserved({ original, candidate: routing });
      requireManualPreserved({ original, candidate: told });
      expect(told.files.some((file) => file.content === intendedAtlasSkill)).toBe(true);
      expect(unrelated.files.some((file) => file.content === intendedAtlasSkill)).toBe(false);
      expect(
        routing.files.some(
          (file) =>
            /(?:AGENTS|CLAUDE)\.md$/.test(file.path) && file.content.includes("Shadowclone"),
        ),
      ).toBe(true);
      expect(told.files.some((file) => file.content.includes("# Shadowclone profile"))).toBe(false);
    }
    const file = path.join(
      reusableLayout(directory).home("routing"),
      ".agents/skills/personal-engineering/SKILL.md",
    );
    expect(await Bun.file(file).text()).toBe(existingManualSkill);
    await Bun.write(file, `${existingManualSkill}\nManual addition.\n`);
    const original = await captureEnvironment({
      directory,
      arm: "skills",
      repository: "atlas",
      engine: "codex",
    });
    const changed = await captureEnvironment({
      directory,
      arm: "routing",
      repository: "atlas",
      engine: "codex",
    });
    expect(() => requireManualPreserved({ original, candidate: changed })).toThrow("manual skill");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}, 30000);

test("private bundle access rejects checkout storage and mismatching seals", async () => {
  await expect(
    readHeldout(path.join(import.meta.dir, "heldout-manifest.json")),
  ).rejects.toThrow("inside a repository");
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-seal-"));
  try {
    const file = path.join(directory, "bundle.json");
    await Bun.write(
      file,
      JSON.stringify({
        protocol: "preference-respect-v3",
        cases: fixtureCases().filter((entry) => entry.split === "held-out"),
      }),
    );
    await expect(readHeldout(file)).rejects.toThrow("published seal");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("authorized learning may append guidance while retaining every original manual instruction", () => {
  const file = {
    root: "home" as const,
    path: ".agents/skills/personal-engineering/SKILL.md",
    encoding: "utf8" as const,
    mode: 0o600,
    content: existingManualSkill,
  };
  const original = { files: [file], fingerprint: "original" };
  const appended = {
    ...file,
    content: `${existingManualSkill}\n## Finishing work\n\nLeave work for review.\n`,
  };
  const candidate = { files: [appended], fingerprint: "candidate" };
  expect(() => requireManualPreserved({ original, candidate })).toThrow("manual skill");
  expect(() =>
    requireManualPreserved({ original, candidate, allowPublishedAdditions: true }),
  ).not.toThrow();
  for (const content of [
    appended.content.replace("Do not add code comments", "Always add code comments"),
    appended.content.replace("name: personal-engineering", "name: different-skill"),
  ]) {
    expect(() =>
      requireManualPreserved({
        original,
        candidate: { ...candidate, files: [{ ...appended, content }] },
        allowPublishedAdditions: true,
      }),
    ).toThrow("manual skill");
  }
  expect(() =>
    requireManualPreserved({
      original,
      candidate: { ...candidate, files: [{ ...appended, mode: 0o777 }] },
      allowPublishedAdditions: true,
    }),
  ).toThrow("manual skill");
});

test("review approval is an explicit fingerprint decision", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-review-"));
  try {
    const file = path.join(directory, "review.json");
    await writeFrozenArtifact({
      file,
      value: {
        fingerprint: "a".repeat(64),
        decision: "draft",
        calibrationFingerprint: "b".repeat(64),
        cases: fixtureCases().map((entry) => ({
          id: entry.task.id,
          family: entry.family,
          split: entry.split,
          specification: entry.specification,
          checks: [],
        })),
      },
    });
    await expect(
      approveCaseReview({ reviewFile: file, fingerprint: "b".repeat(64) }),
    ).rejects.toThrow("fingerprint");
    expect(
      (await approveCaseReview({ reviewFile: file, fingerprint: "a".repeat(64) })).decision,
    ).toBe("approved");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("corpus preparation is synthetic and contains excluded tool-result decoys", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-corpus-"));
  try {
    await prepareManualEnvironment({ directory, arm: "deep-0", routed: true });
    await materializeCorpus({ directory, preparation: 0 });
    const paths = reusableLayout(directory).paths("deep-0");
    const decoy = await Bun.file(
      path.join(paths.claudeProjectsDirectory, "synthetic-atlas/excluded-tool-output.jsonl"),
    ).text();
    expect(decoy).toContain("tool_result");
    expect(decoy).toContain("force push");
    expect(decoy).not.toContain("acceptance.test.ts");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
