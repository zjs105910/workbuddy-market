import { expect, test } from "bun:test";
import { mkdir, mkdtemp, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { resolveArtifactPath, resolveInstallTarget } from "./installTarget";

async function scratch(prefix: string): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), `shadowclone-${prefix}-`));
}

async function gitRepository(): Promise<string> {
  const directory = await scratch("target");
  const init = Bun.spawn({
    cmd: ["git", "-C", directory, "init"],
    stdout: "ignore",
    stderr: "ignore",
  });

  expect(await init.exited).toBe(0);

  return directory;
}

test("a recorded repository root resolves", async () => {
  const directory = await gitRepository();

  expect(await resolveInstallTarget({ directory })).not.toBeNull();
});

test("a relative recorded directory is refused", async () => {
  expect(await resolveInstallTarget({ directory: "some/repo" })).toBeNull();
});

test("a recorded directory that no longer exists is refused", async () => {
  const directory = await scratch("missing");

  expect(
    await resolveInstallTarget({ directory: path.join(directory, "gone") }),
  ).toBeNull();
});

test("a recorded directory that is not a repository is refused", async () => {
  const directory = await scratch("plain");

  expect(await resolveInstallTarget({ directory })).toBeNull();
});

test("a subdirectory of a repository is refused as a root", async () => {
  const directory = await gitRepository();
  const nested = path.join(directory, "packages", "app");

  await mkdir(nested, { recursive: true });

  expect(await resolveInstallTarget({ directory: nested })).toBeNull();
});

test("a symbolic link pointing at an unrelated repository is refused", async () => {
  const real = await gitRepository();
  const container = await scratch("link");
  const link = path.join(container, "repo");

  await symlink(real, link);

  const resolved = await resolveInstallTarget({ directory: link });

  expect(resolved).not.toBe(link);
});

test("an artifact path inside the root resolves", async () => {
  const root = await gitRepository();

  const resolved = await resolveArtifactPath({
    root,
    relativePath: path.join(".claude", "agents", "shadowclone.md"),
  });

  expect(resolved).toBe(path.join(root, ".claude", "agents", "shadowclone.md"));
});

test("an artifact whose parent is a symbolic link is refused", async () => {
  const root = await gitRepository();
  const outside = await scratch("outside");

  await mkdir(path.join(outside, "agents"), { recursive: true });
  await writeFile(path.join(outside, "agents", "shadowclone.md"), "important");
  await symlink(outside, path.join(root, ".claude"));

  const resolved = await resolveArtifactPath({
    root,
    relativePath: path.join(".claude", "agents", "shadowclone.md"),
  });

  expect(resolved).toBeNull();
  expect(
    await Bun.file(path.join(outside, "agents", "shadowclone.md")).exists(),
  ).toBeTrue();
});

test("an artifact that is itself a symbolic link is refused", async () => {
  const root = await gitRepository();
  const outside = await scratch("outside-file");
  const target = path.join(outside, "important.md");

  await writeFile(target, "important");
  await mkdir(path.join(root, ".claude", "agents"), { recursive: true });
  await symlink(target, path.join(root, ".claude", "agents", "shadowclone.md"));

  const resolved = await resolveArtifactPath({
    root,
    relativePath: path.join(".claude", "agents", "shadowclone.md"),
  });

  expect(resolved).toBeNull();
});

test("a traversing relative path is refused", async () => {
  const root = await gitRepository();

  expect(
    await resolveArtifactPath({
      root,
      relativePath: path.join("..", "..", "etc", "hosts"),
    }),
  ).toBeNull();
});
