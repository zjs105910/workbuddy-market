import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { isolatedCodexHome, returnRefreshedLogin, userCodexHome } from "./codexHome";

test("an isolated codex home carries authentication and no personal guidance", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "codex-home-"));
  const userHome = path.join(root, "home");
  const source = path.join(userHome, ".codex");

  await mkdir(path.join(source, "skills", "clean-code"), { recursive: true });
  await Bun.write(path.join(source, "auth.json"), '{"token":"fixture"}');
  await Bun.write(path.join(source, "AGENTS.md"), "personal instructions");
  await Bun.write(path.join(source, "config.toml"), 'model = "fixture"\n');
  await Bun.write(
    path.join(source, "skills", "clean-code", "SKILL.md"),
    "Write zero comments.",
  );

  try {
    const isolated = await isolatedCodexHome({
      temporaryDirectory: root,
      environment: {},
      userHome,
    });

    expect(await Bun.file(path.join(isolated, "auth.json")).text()).toBe(
      '{"token":"fixture"}',
    );

    for (const leaked of [
      "AGENTS.md",
      "config.toml",
      "skills/clean-code/SKILL.md",
    ]) {
      expect(await Bun.file(path.join(isolated, leaked)).exists()).toBeFalse();
    }

    expect(isolated.startsWith(root)).toBeTrue();
    expect(isolated).not.toBe(source);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("the user codex home is used when no isolation directory is given", () => {
  expect(userCodexHome({ environment: {}, userHome: "/home/person" })).toBe(
    "/home/person/.codex",
  );
  expect(userCodexHome({ environment: { CODEX_HOME: "/custom" } })).toBe(
    "/custom",
  );
});

test("a login that Codex refreshed during a run goes back to the user's home, unless the home changed meanwhile", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "codex-login-"));
  const sourceHome = path.join(root, "source");
  const isolatedHome = path.join(root, "isolated");

  await mkdir(sourceHome, { recursive: true });
  await mkdir(isolatedHome, { recursive: true });

  try {
    await Bun.write(path.join(sourceHome, "auth.json"), '{"refresh":"first"}');
    await Bun.write(path.join(isolatedHome, "auth.json"), '{"refresh":"second"}');
    await returnRefreshedLogin({ isolatedHome, sourceHome, original: '{"refresh":"first"}' });

    expect(await Bun.file(path.join(sourceHome, "auth.json")).text()).toBe('{"refresh":"second"}');

    await Bun.write(path.join(sourceHome, "auth.json"), '{"refresh":"from another login"}');
    await Bun.write(path.join(isolatedHome, "auth.json"), '{"refresh":"third"}');
    await returnRefreshedLogin({ isolatedHome, sourceHome, original: '{"refresh":"second"}' });

    expect(await Bun.file(path.join(sourceHome, "auth.json")).text()).toBe('{"refresh":"from another login"}');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
