import { expect, test } from "bun:test";
import type { EngineRunner } from "@shadowclone/agents";
import {
  explicitProfileEvidence,
  profileEvidenceId,
  type ProfileRule,
} from "@shadowclone/profile";
import { consolidateNewRules } from "./consolidate";

function rule(sessionIndex: number): ProfileRule {
  const evidence = profileEvidenceId({
    originId: "github.com/acme",
    sessionId: `session-${sessionIndex}`,
    timestamp: 1_788_537_600_000 + sessionIndex,
    kind: "question-answered",
    category: "agent-question",
  });

  return {
    key: `rule-${sessionIndex}`,
    title: `Prefer small changes ${sessionIndex}`,
    body: "Choose the smallest change that satisfies the request.",
    section: "workflow",
    scope: "org",
    originDirectory: "github.com--acme--936913df4a5c268b",
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
}

test("retains the first key and unions exact constituent evidence", async () => {
  const runner: EngineRunner = () =>
    Promise.resolve({
      engine: "claude-code",
      sessionId: "merge-session",
      transcriptPath: null,
      text: "",
      structured: {
        rules: [
          {
            title: "Prefer small changes",
            body: "Choose the smallest change that satisfies the request.",
            section: "workflow",
            sources: [0, 1, 2],
          },
        ],
      },
      costUsd: 0.01,
      durationMs: 10,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    });

  const { rules: consolidated } = await consolidateNewRules({
    rules: [rule(1), rule(2), rule(3)],
    runner,
    workingDirectory: "/tmp",
  });

  expect(consolidated).toHaveLength(1);
  expect(consolidated[0]?.key).toBe("rule-1");
  expect(consolidated[0]?.evidence.for).toHaveLength(3);
  expect(consolidated[0]?.sessions).toBe(3);
  expect(consolidated[0]?.status).toBe("active");
});

test("keeps explicit guidance active when consolidating fewer than three sessions", async () => {
  const runner: EngineRunner = () =>
    Promise.resolve({
      engine: "claude-code",
      sessionId: "merge-session",
      transcriptPath: null,
      text: "",
      structured: {
        rules: [
          {
            title: "Prefer small changes",
            body: "Choose the smallest change that satisfies the request.",
            section: "workflow",
            sources: [0, 1],
          },
        ],
      },
      costUsd: 0.01,
      durationMs: 10,
      turns: 1,
      isError: false,
      permissionDenials: [],
      actions: [],
      errorMessage: null,
    });

  const first = rule(1);

  const explicit = {
    ...first,
    evidence: {
      ...first.evidence,
      for: first.evidence.for.map(explicitProfileEvidence),
    },
  };

  const { rules: consolidated } = await consolidateNewRules({
    rules: [explicit, rule(2)],
    runner,
    workingDirectory: "/tmp",
  });

  expect(consolidated).toHaveLength(1);
  expect(consolidated[0]?.sessions).toBe(2);
  expect(consolidated[0]?.status).toBe("active");
});
