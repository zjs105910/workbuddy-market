import { expect, test } from "bun:test";
import path from "node:path";
import { rm } from "node:fs/promises";
import { readConfig, writeConfig } from "@shadowclone/core";
import { normalizeRemoteRepository } from "@shadowclone/sessions";
import { skillFixture } from "./testing";
import { explainLearningEnvironment } from "./diagnostics";
import { learningRecord } from "./fixtures";
import { recordFingerprint } from "./records";
import { writeEnvironment } from "./store";
import { emptyEnvironment, type LearningRecord } from "./types";

test("context explanations use the disposition for the current repository", async () => {
  const setup = await skillFixture();

  try {
    const remote = "https://github.com/synthetic/second.git";
    const identity = normalizeRemoteRepository(remote);
    if (!identity?.profileFileName) throw new Error("Expected synthetic repository identity");

    const initial = learningRecord();
    const record: LearningRecord = { ...initial, rule: {
      ...initial.rule, scope: "org", originDirectory: identity.origin.directoryName, repositoryName: null,
    } };
    const config = await readConfig({ configPath: setup.paths.configFile });
    await writeConfig({ configPath: setup.paths.configFile, config: {
      ...config, sources: { ...config.sources, "git-metadata": true },
    } });
    const firstScope = `${identity.origin.directoryName}/first`;
    const secondScope = `${identity.origin.directoryName}/${identity.profileFileName}`;

    await writeEnvironment({ paths: setup.paths, state: {
      ...emptyEnvironment, phase: "active", records: [record],
      repositories: [
        { directory: path.join(setup.home, "first"), originDirectory: identity.origin.directoryName, repositoryName: "first" },
        { directory: setup.cwd, originDirectory: identity.origin.directoryName, repositoryName: identity.profileFileName },
      ],
      dispositions: [
        { key: record.rule.key, scope: firstScope, inputFingerprint: recordFingerprint(record), status: "published", reason: "Published in the first repository", destinations: [] },
        { key: record.rule.key, scope: secondScope, inputFingerprint: recordFingerprint(record), status: "pending", reason: "Second repository needs a reviewer", destinations: [] },
      ],
    } });

    const explanation = await explainLearningEnvironment({ ...setup, readRemote: async () => remote });
    expect(explanation).toContain("Second repository needs a reviewer");
    expect(explanation).not.toContain("Published in the first repository");
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
