import { expect, test } from "bun:test";
import path from "node:path";
import { integrationFixture } from "@shadowclone/core/testing";
import type { CorrectionSignal } from "@shadowclone/sessions";
import { materializeEvidence } from "./excerpts";

test("user steering crosses the pointer redaction gate and excludes generated learning input", async () => {
  const { home } = await integrationFixture();
  const secret = `sk-ant-${"A".repeat(90)}`;
  const sourcePath = path.join(home, "messages.jsonl");
  const rows = [
    `Always keep API tokens private: ${secret}`,
    "SHADOWCLONE_INTERNAL_LEARNING generated evidence",
    "# Shadowclone profile\nGenerated preference",
  ];

  await Bun.write(sourcePath, rows.join("\n"));

  let byteOffset = 0;

  const signals: CorrectionSignal[] = rows.map((row, position) => {
    const textRef = {
      type: "file" as const,
      sourcePath,
      byteOffset,
      byteLength: Buffer.byteLength(row),
    };

    byteOffset += textRef.byteLength + 1;

    return {
      kind: "user-steering",
      category: "user-episode",
      label: "user episode",
      sessionId: `session-${position}`,
      timestamp: position,
      origin: { id: "local", directoryName: "local", promotable: false },
      repositoryName: null,
      textRefs: [textRef],
    };
  });

  const materialized = await materializeEvidence({
    signals,
    sourceRoots: [home],
  });

  expect(materialized.signals).toHaveLength(1);
  expect([...materialized.excerpts.values()].join("\n")).not.toContain(secret);
  expect([...materialized.excerpts.values()].join("\n")).toContain(
    "Always keep API tokens private",
  );

  const revoked = await materializeEvidence({
    signals,
    sourceRoots: [home],
    authorizeRef: async () => false,
  });

  expect(revoked.signals).toHaveLength(0);
  expect(revoked.excerpts.size).toBe(0);
});
