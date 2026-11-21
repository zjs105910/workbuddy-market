import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { FileTextRef, CorrectionSignal } from "@shadowclone/sessions";
import { createProjectPaths } from "@shadowclone/core";
import { materializeEvidence } from "../excerpts";
import { createReconciliationContext } from "./context";
import { buildReconciliationPrompt } from "./prompt";
import { readProfileSnapshot } from "@shadowclone/environment";

async function writeRef(options: {
  readonly filePath: string;
  readonly text: string;
}): Promise<FileTextRef> {
  await Bun.write(options.filePath, options.text);

  return {
    type: "file",
    sourcePath: options.filePath,
    byteOffset: 0,
    byteLength: Bun.file(options.filePath).size,
  };
}

test("labels the presented plan as context and keeps only the user response as evidence", async () => {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-prompt-context-"),
  );
  const paths = createProjectPaths({ homeDirectory, platform: "darwin" });
  const origin = {
    id: "github.com/acme",
    directoryName: "github.com--acme--936913df4a5c268b",
    promotable: true,
  };
  const signal: CorrectionSignal = {
    kind: "plan-resolved",
    category: "presented-plan",
    label: "a presented plan",
    sessionId: "session",
    timestamp: 1,
    origin,
    repositoryName: null,
    textRefs: [
      await writeRef({
        filePath: path.join(homeDirectory, "response.txt"),
        text: "Use pnpm for every install in this repository.",
      }),
    ],
    contextRefs: [
      await writeRef({
        filePath: path.join(homeDirectory, "plan.txt"),
        text: "Plan: run npm install, then add the dependency.",
      }),
    ],
  };
  const { excerpts } = await materializeEvidence({
    signals: [signal],
    sourceRoots: [homeDirectory],
  });
  const prompt = await buildReconciliationPrompt({
    context: createReconciliationContext({
      batch: { origin, repositoryName: null, signals: [signal] },
      profile: await readProfileSnapshot(paths),
      library: {
        guidance: [],
        preferences: [],
        skills: [],
        axes: [],
        independentSkills: [],
      },
    }),
    excerpts,
  });
  const [, afterEvidenceLabel] = prompt.split("User evidence:\n");
  const [userEvidence, afterContextLabel] = (afterEvidenceLabel ?? "").split(
    "Preceding assistant context (not user evidence):\n",
  );

  expect(userEvidence).toContain("Use pnpm for every install");
  expect(userEvidence).not.toContain("npm install");
  expect(afterContextLabel).toContain("Plan: run npm install");
});
