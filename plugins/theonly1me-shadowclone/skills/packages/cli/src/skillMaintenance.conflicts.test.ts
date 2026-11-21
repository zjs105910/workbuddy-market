import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import path from "node:path";
import { updateLearningEnvironment } from "@shadowclone/learning";
import { readEnvironment, writeEnvironment } from "@shadowclone/environment";
import { learningRecord } from "@shadowclone/environment/testing";
import { listSkillProposals } from "@shadowclone/skills";
import { conflictExecution, conflictFixture } from "@shadowclone/learning/testing";

test("the CLI lists scoped learning and conflict proposals together and shows the supporting decision", async () => {
  const setup = await conflictFixture();

  try {
    await updateLearningEnvironment({ ...setup, execution: conflictExecution() });
    const [proposal] = await listSkillProposals(setup.paths);
    const state = await readEnvironment(setup.paths);
    if (!proposal || !state) throw new Error("Expected the synthetic review state");

    const record = learningRecord({ key: "unmatched-learning" });
    await writeEnvironment({ paths: setup.paths, state: {
      ...state,
      records: [{ ...record, rule: { ...record.rule, scope: "org", originDirectory: "synthetic-owner", repositoryName: null } }],
    } });

    const scriptPath = path.join(setup.home, "isolated-cli.ts");
    await Bun.write(scriptPath, [
      `import { createProjectPaths, projectPaths } from ${JSON.stringify(Bun.resolveSync("@shadowclone/core", import.meta.dir))};`,
      `Object.assign(projectPaths, createProjectPaths({ homeDirectory: ${JSON.stringify(setup.home)}, platform: process.platform }));`,
      `await import(${JSON.stringify(path.join(import.meta.dir, "main.ts"))});`,
    ].join("\n"));
    const run = async (arguments_: string[]) => {
      const child = Bun.spawn({
        cmd: [process.execPath, scriptPath, "skills", ...arguments_],
        cwd: setup.cwd,
        stdout: "pipe", stderr: "pipe",
      });
      const [stdout, stderr, exitCode] = await Promise.all([
        new Response(child.stdout).text(), new Response(child.stderr).text(), child.exited,
      ]);
      expect(stderr).toBe("");
      expect(exitCode).toBe(0);
      return stdout;
    };

    const pending = await run(["pending"]);
    expect(pending).toContain(proposal.id);
    expect(pending).toContain("unmatched-learning");
    expect(pending).toContain("unresolved-scope");
    expect(await run(["show", proposal.id])).toContain("Decide whether dependency tables belong");
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
