import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultManagedPolicy, createProjectPaths } from "@shadowclone/core";
import type { EngineRunner } from "@shadowclone/agents";
import { explicitProfileEvidence, profileEvidenceId, type ProfileRule } from "@shadowclone/profile";
import { runDeepLearning } from "./deepLearn";
import { readProfileSnapshot, writeProfile } from "@shadowclone/environment";

test("deep refresh activates stored candidates backed by explicit guidance", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-deep-migration-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const evidence = explicitProfileEvidence(
    profileEvidenceId({
      originId: "github.com/acme",
      sessionId: "session-1",
      timestamp: 1_788_537_600_000,
      kind: "user-steering",
      category: "user-episode",
    }),
  );
  const rule: ProfileRule = {
    key: "explicit-rule",
    title: "Prefer small changes",
    body: "Choose the smallest coherent change.",
    section: "workflow",
    scope: "org",
    originDirectory: "github.com--acme",
    repositoryName: null,
    source: "mined",
    status: "candidate",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [evidence], against: [] },
    observations: 1,
    sessions: 1,
    origins: ["github.com/acme"],
    lastSeen: "2026-09-05",
    importReference: null,
  };

  await writeProfile({ paths, rules: [rule] });

  const lines: string[] = [];
  const runner: EngineRunner = () => {
    throw new Error("Profile migration must not call the engine");
  };

  const result = await runDeepLearning({
    signals: [],
    events: [],
    paths,
    policy: defaultManagedPolicy,
    runner,
    engine: "claude-code",
    dryRun: false,
    apply: true,
    writeLine: (line) => {
      lines.push(line);
    },
  });
  const profile = await readProfileSnapshot(paths);

  expect(result.networkCallsMade).toBeFalse();
  expect(result.profileUpdated).toBeTrue();
  expect(profile.rules[0]?.rule.status).toBe("active");
  expect(lines).toContain("Activated 1 explicit profile rule(s).");
});
