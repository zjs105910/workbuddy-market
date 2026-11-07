import { expect, test } from "bun:test";
import path from "node:path";
import { rm } from "node:fs/promises";
import { integrationFixture } from "@shadowclone/core/testing";
import { installIntegration, uninstallIntegration } from "./install";
import { refreshIntegrations, integrationHealth } from "./refresh";
import { nativeSessionEnd } from "./hooks";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { emptyEnvironment } from "../environment/types";
import { writeEnvironment } from "../environment/store";
import { readIntegrations } from "./state";

test("refresh recognizes a shared skill updated by its other owning harness", async () => {
  const fixture = await integrationFixture();
  try {
    await installIntegration({ ...fixture, agent: "codex", scope: "global" });
    await installIntegration({ ...fixture, agent: "pi", scope: "global" });
    await writeEnvironment({ paths: fixture.paths, state: { ...emptyEnvironment, phase: "active" } });
    expect(await refreshIntegrations(fixture)).toEqual({ refreshed: 2, preserved: 0 });
    expect((await integrationHealth(fixture)).every(line => line.includes(": installed;"))).toBeTrue();
  } finally { await rm(fixture.home, { recursive: true, force: true }); }
});

test("Pi installs owned global and repository files and preserves surrounding guidance and resources", async () => {
  const fixture = await integrationFixture();
  const destination = path.join(fixture.cwd, "AGENTS.md");
  const resource = path.join(fixture.cwd, ".agents/skills/manual/example.txt");
  await Bun.write(destination, "Manual team guidance\n");
  await Bun.write(resource, "Manual resource\n");
  try {
    const global = await installIntegration({ ...fixture, agent: "pi", scope: "global" });
    const local = await installIntegration({ ...fixture, agent: "pi", scope: "repository" });
    expect(await Bun.file(path.join(fixture.paths.piAgentDirectory, "extensions/shadowclone.js")).text()).toContain("agent_settled");
    expect(await Bun.file(destination).text()).toContain("Manual team guidance");
    expect(await refreshIntegrations(fixture)).toEqual({ refreshed: 2, preserved: 0 });
    expect((await integrationHealth(fixture)).every(line => line.includes(": installed;"))).toBeTrue();
    const repeated = await installIntegration({ ...fixture, agent: "pi", scope: "repository" });
    expect(repeated.id).toBe(local.id);
    await uninstallIntegration({ paths: fixture.paths, integration: repeated });
    await uninstallIntegration({ paths: fixture.paths, integration: global });
    expect(await Bun.file(destination).text()).toBe("Manual team guidance\n");
    expect(await Bun.file(resource).text()).toBe("Manual resource\n");
    expect(await Bun.file(path.join(fixture.paths.piAgentDirectory, "extensions/shadowclone.js")).exists()).toBeFalse();
  } finally { await rm(fixture.home, { recursive: true, force: true }); }
});

test("Pi shares the managed global skill with Codex and refuses edited extension removal", async () => {
  const fixture = await integrationFixture();
  try {
    const codex = await installIntegration({ ...fixture, agent: "codex", scope: "global" });
    const pi = await installIntegration({ ...fixture, agent: "pi", scope: "global" });
    const skill = path.join(fixture.home, ".agents/skills/shadowclone-context/SKILL.md");
    await uninstallIntegration({ paths: fixture.paths, integration: codex });
    expect(await Bun.file(skill).exists()).toBeTrue();
    const extension = path.join(fixture.paths.piAgentDirectory, "extensions/shadowclone.js");
    const original = await Bun.file(extension).text();
    await Bun.write(extension, `${original}\nUser edit\n`);
    expect(await refreshIntegrations(fixture)).toEqual({ refreshed: 0, preserved: 1 });
    await expect(uninstallIntegration({ paths: fixture.paths, integration: pi })).rejects.toThrow("preserving");
    expect(await Bun.file(extension).text()).toContain("User edit");
    await Bun.write(extension, original);
    await uninstallIntegration({ paths: fixture.paths, integration: pi });
    expect(await Bun.file(skill).exists()).toBeFalse();
  } finally { await rm(fixture.home, { recursive: true, force: true }); }
});

test("Pi lifecycle learning requires capture consent and honors the repository installation", async () => {
  const fixture = await integrationFixture();
  try {
    const global = await installIntegration({ ...fixture, agent: "pi", scope: "global" });
    const local = await installIntegration({ ...fixture, agent: "pi", scope: "repository" });
    const input = JSON.stringify({ cwd: fixture.cwd, session_id: "synthetic" });
    expect(await nativeSessionEnd({ ...fixture, id: local.id, input })).toBeNull();
    await writeConfig({ configPath: fixture.paths.configFile, config: { ...defaultConfig, sources: { ...defaultConfig.sources, pi: true } } });
    expect(await nativeSessionEnd({ ...fixture, id: global.id, input })).toBeNull();
    expect(await nativeSessionEnd({ ...fixture, id: local.id, input })).toBeString();
  } finally { await rm(fixture.home, { recursive: true, force: true }); }
});

test("uninstall transfers current shared skill ownership after another harness preserves an edited extension", async () => {
  const fixture = await integrationFixture();
  try {
    await installIntegration({ ...fixture, agent: "codex", scope: "global" });
    const pi = await installIntegration({ ...fixture, agent: "pi", scope: "global" });
    const extension = path.join(fixture.paths.piAgentDirectory, "extensions/shadowclone.js");
    const original = await Bun.file(extension).text();
    await Bun.write(extension, `${original}\nUser edit\n`);
    await writeEnvironment({ paths: fixture.paths, state: { ...emptyEnvironment, phase: "active" } });
    expect(await refreshIntegrations(fixture)).toEqual({ refreshed: 1, preserved: 1 });
    await Bun.write(extension, original);
    const integrations = await readIntegrations(fixture.paths);
    const codex = integrations.find(integration => integration.agent === "codex");
    if (!codex) throw new Error("Missing refreshed Codex integration");
    const skill = path.join(fixture.home, ".agents/skills/shadowclone-context/SKILL.md");
    await uninstallIntegration({ paths: fixture.paths, integration: codex });
    expect(await Bun.file(skill).exists()).toBeTrue();
    const remaining = (await readIntegrations(fixture.paths)).find(integration => integration.id === pi.id);
    if (!remaining) throw new Error("Missing remaining Pi integration");
    await expect(uninstallIntegration({ paths: fixture.paths, integration: pi })).resolves.toBeUndefined();
    expect(await Bun.file(skill).exists()).toBeFalse();
  } finally { await rm(fixture.home, { recursive: true, force: true }); }
});
