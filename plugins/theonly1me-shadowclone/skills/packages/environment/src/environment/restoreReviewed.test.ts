import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { renderProfileRule } from "@shadowclone/profile";
import { renderProfileRejections } from "@shadowclone/profile";
import type { ProfileRule } from "@shadowclone/profile";
import { restoreReviewedMemoryRules } from "@shadowclone/profile";
import { undoRevision } from "./undo";

test("reviewed routing restoration preserves manual text and is reversible", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "memory-routing-"));

  try {
    const paths = createProjectPaths({
      homeDirectory: directory,
      platform: "darwin",
    });

    const rule: ProfileRule = {
      key: "claude-memory:feedback_load_skills",
      title: "Load skills",
      body: "Load clean-code before editing.",
      section: "workflow",
      scope: "global",
      originDirectory: null,
      repositoryName: null,
      source: "user",
      status: "active",
      proposal: null,
      appliesWhen: [],
      evidence: { for: [], against: [] },
      observations: 0,
      lastSeen: "imported",
      sessions: 0,
      origins: [],
      importReference: null,
    };

    const rejected = renderProfileRejections([
      {
        relativePath: "global/workflow.md",
        key: rule.key,
        title: rule.title,
        body: rule.body,
        source: "user",
        importReference: null,
        reason: "skill-covered",
      },
    ]);

    await Bun.write(paths.rejectedProfileFile, rejected);

    const target = path.join(paths.profileDirectory, "global/workflow.md");

    await Bun.write(target, "# Manual notes\n\nPreserve this note.\n");

    const revisionId = await restoreReviewedMemoryRules({
      paths,
      rules: [rule],
    });

    if (!revisionId) {
      throw new Error("Expected profile revision");
    }

    expect(await Bun.file(target).text()).toContain("Preserve this note.");
    expect(await Bun.file(target).text()).toContain(rule.body);
    expect(await Bun.file(paths.rejectedProfileFile).text()).not.toContain(
      rule.key,
    );

    await undoRevision({ paths, id: revisionId });

    expect(await Bun.file(target).text()).toBe(
      "# Manual notes\n\nPreserve this note.\n",
    );
    expect(await Bun.file(paths.rejectedProfileFile).text()).toBe(rejected);

    await Bun.write(target, renderProfileRule(rule));
    await expect(
      restoreReviewedMemoryRules({ paths, rules: [rule] }),
    ).rejects.toThrow("conflicts with existing guidance");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
