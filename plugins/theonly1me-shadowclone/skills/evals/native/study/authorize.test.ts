import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, setSourceEnabled, writeConfig } from "@shadowclone/core";
import { authorizeStudy } from "./authorize";

test("the study needs consent for the skill library, agent context, sessions, and deep learning", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "study-authorize-"));

  try {
    const configPath = path.join(directory, "config.toml");
    const enabled = ["agent-context", "skill-library", "claude-code"] as const;
    const config = enabled.reduce((current, source) => setSourceEnabled({ config: current, source, enabled: true }), defaultConfig);
    await writeConfig({ config, configPath });
    await expect(authorizeStudy({ configPath, managedConfigPath: null })).rejects.toThrow("requires enabled");

    await writeConfig({ config: { ...config, distillation: { ...config.distillation, deep: true } }, configPath });
    await expect(authorizeStudy({ configPath, managedConfigPath: null })).resolves.toBeUndefined();

    await writeConfig({ config: setSourceEnabled({ config: { ...config, distillation: { ...config.distillation, deep: true } }, source: "skill-library", enabled: false }), configPath });
    await expect(authorizeStudy({ configPath, managedConfigPath: null })).rejects.toThrow("requires enabled");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
