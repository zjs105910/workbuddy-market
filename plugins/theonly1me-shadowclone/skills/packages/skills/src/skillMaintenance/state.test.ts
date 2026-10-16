import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import {
  readMaintenanceState,
  showSkillRoots,
  writeMaintenanceState,
} from "./state";

test("ignores the redundant Codex root and renders structural root details", async () => {
  const home = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-skill-state-"),
  );
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const codexId = "a".repeat(64);
  const claudeId = "b".repeat(64);

  await writeMaintenanceState({
    paths,
    state: {
      version: 1,
      roots: [
        {
          id: codexId,
          directory: path.join(home, ".codex/skills"),
          cwd: home,
          scope: "global",
          owner: "user",
          destination: path.join(home, ".codex/skills"),
          enabled: true,
        },
        {
          id: claudeId,
          directory: path.join(home, ".claude/skills"),
          cwd: home,
          scope: "global",
          owner: "user",
          destination: path.join(home, ".claude/skills"),
          enabled: true,
        },
      ],
      tracked: [
        {
          id: "tracked-codex",
          rootId: codexId,
          relativePath: "review/SKILL.md",
          fingerprint: "fingerprint",
          kind: "amend",
          automatic: false,
        },
      ],
      assessed: {},
      findings: {},
      rejected: {},
    },
  });

  const state = await readMaintenanceState(paths);

  expect(state.roots.map((root) => root.id)).toEqual([claudeId]);
  expect(state.tracked).toEqual([]);

  const rendered = await showSkillRoots(paths);

  expect(rendered).toContain(claudeId);
  expect(rendered).not.toContain(home);
});
