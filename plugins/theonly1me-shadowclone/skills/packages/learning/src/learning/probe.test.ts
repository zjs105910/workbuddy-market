import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { integrationFilePath } from "@shadowclone/environment";
import { readLatestProbe, runLearningProbe } from "./probe";
import { probeFixture, probeResponse } from "./probe.fixtures";

for (const engine of ["claude-code", "codex"] as const) {
  test(`${engine} probe uses installed native guidance, separates loading and behavior, and cleans up`, async () => {
    const setup = await probeFixture(engine);
    let privateHome = "";
    let calls = 0;
    try {
      const receipt = await runLearningProbe({
        ...setup, key: setup.record.rule.key, engine,
        task: "Is the sample ready?", expected: "PINEAPPLE_READY", approved: true,
        runner: async (options) => {
          calls += 1;
          privateHome = options.homeDirectory;
          expect(options.prompt).toBe("Is the sample ready?");
          expect(options.prompt).not.toContain("PINEAPPLE_READY");
          expect(options.access).toBe("read");
          expect(options.persistSession).toBeFalse();
          expect(options.blockedPaths).toContain(setup.cwd);
          const instructions = path.join(options.homeDirectory,
            engine === "claude-code" ? ".claude/CLAUDE.md" : ".codex/AGENTS.md");
          expect(await Bun.file(instructions).text()).toContain(setup.record.rule.body);
          return probeResponse(engine);
        },
      });
      expect(calls).toBe(1);
      expect(receipt.outcome).toBe("pass");
      expect(receipt.hooksTested).toBeFalse();
      expect(receipt.skillReadObserved).toBeFalse();
      expect(await readLatestProbe(setup.paths)).toEqual(receipt);
      expect(await Bun.file(path.join(privateHome, engine === "claude-code" ? ".claude/CLAUDE.md" : ".codex/AGENTS.md")).exists()).toBeFalse();
      expect(JSON.stringify(receipt)).not.toContain("PINEAPPLE_READY");
      expect(JSON.stringify(receipt)).not.toContain(setup.home);
    } finally {
      await rm(setup.root, { recursive: true, force: true });
    }
  });
}

test("probes stop before model access without approval, consent, or current owned native guidance", async () => {
  const setup = await probeFixture("codex");
  let calls = 0;
  const options = {
    ...setup, key: setup.record.rule.key, engine: "codex" as const,
    task: "Is the sample ready?", expected: "PINEAPPLE_READY", approved: true,
    runner: async () => { calls += 1; return probeResponse("codex"); },
  };
  try {
    await expect(runLearningProbe({ ...options, approved: false })).rejects.toThrow("authorize one paid");
    const file = setup.integration.files.find((entry) => entry.kind === "instructions");
    if (!file) throw new Error("Expected native instructions");
    await Bun.write(integrationFilePath({ integration: setup.integration, file }), "Edited managed text\n");
    await expect(runLearningProbe(options)).rejects.toThrow("edited");
    await writeConfig({ configPath: setup.paths.configFile, config: defaultConfig });
    await expect(runLearningProbe(options)).rejects.toThrow("consent");
    expect(calls).toBe(0);
  } finally {
    await rm(setup.root, { recursive: true, force: true });
  }
});

test("a mismatch or engine error cannot produce a passed behavior receipt", async () => {
  const setup = await probeFixture("codex");
  const options = { ...setup, key: setup.record.rule.key, engine: "codex" as const,
    task: "Is the sample ready?", expected: "PINEAPPLE_READY", approved: true };
  try {
    expect((await runLearningProbe({ ...options, runner: async () => ({ ...probeResponse("codex"), text: "A different answer" }) })).outcome).toBe("fail");
    expect((await runLearningProbe({ ...options, runner: async () => { throw new Error("Synthetic provider failure"); } })).outcome).toBe("error");
  } finally {
    await rm(setup.root, { recursive: true, force: true });
  }
});
