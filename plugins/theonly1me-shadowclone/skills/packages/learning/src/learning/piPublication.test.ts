import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import path from "node:path";
import { resolveLearningExecution } from "./execution";
import {
  emptyEnvironment,
  installIntegration,
  nativeSessionStart,
  readEnvironment,
  writeEnvironment,
} from "@shadowclone/environment";
import { learningRecord, skillEngineRun, skillFixture } from "@shadowclone/environment/testing";
import { updateLearningEnvironment } from "./environmentUpdate/update";
import { fingerprint } from "@shadowclone/core";

test("Pi learning publishes shared skills and native routing for the next session", async () => {
  const fixture = await skillFixture();
  const record = learningRecord({ body: "Use complete parameter names when editing typed code." });
  const supportingFile = path.join(fixture.directory, "examples.txt");
  await Bun.write(supportingFile, "Manually maintained synthetic example\n");
  try {
    await writeEnvironment({ paths: fixture.paths, state: { ...emptyEnvironment, phase: "active", automatic: true, records: [record] } });
    await installIntegration({ ...fixture, agent: "codex", scope: "global" });
    const pi = await installIntegration({ ...fixture, agent: "pi", scope: "global" });
    let calls = 0;
    const { execution } = await resolveLearningExecution({
      engine: "pi",
      model: "session-provider/local",
      allowedEngines: ["pi"],
      runner: async options => {
        calls += 1;
        expect(options.allowedTools).toEqual([]);
        expect(options.model).toBe("session-provider/local");
        const structured = options.prompt.includes("Organize durable") ? {
          routes: [{ key: record.rule.key, destination: "skill", skillId: fingerprint(fixture.filePath), name: "typed-changes", description: "Use for typed code changes.", reason: "Applies to this workflow" }],
        } : {
          outcomes: [{ key: record.rule.key, disposition: "apply", reason: "Supported" }],
          description: "Use complete parameter names when changing typed code.", body: "",
          edits: [{ before: "Preserve the requested behavior.", after: `Preserve the requested behavior. ${record.rule.body}`, keys: [record.rule.key] }],
        };
        return { ...skillEngineRun(structured), engine: "pi", costUsd: null };
      },
    });
    expect((await updateLearningEnvironment({ ...fixture, execution }))?.applied).toBe(1);
    const skillPath = path.join(fixture.home, ".agents/skills/typed-changes/SKILL.md");
    expect(await Bun.file(skillPath).text()).toContain(record.rule.body);
    expect(await Bun.file(path.join(fixture.paths.piAgentDirectory, "AGENTS.md")).text()).toContain("typed-changes");
    expect(await Bun.file(supportingFile).text()).toBe("Manually maintained synthetic example\n");
    expect((await readEnvironment(fixture.paths))?.dispositions[0]?.status).toBe("published");
    const next = await nativeSessionStart({ ...fixture, id: pi.id, input: JSON.stringify({ cwd: fixture.cwd, session_id: "next-synthetic-session" }) });
    expect(next).toEqual({});
    await updateLearningEnvironment({ ...fixture, execution });
    expect(calls).toBe(2);
  } finally { await rm(fixture.home, { recursive: true, force: true }); }
});
