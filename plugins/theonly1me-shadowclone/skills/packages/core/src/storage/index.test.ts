import { expect, test } from "bun:test";
import {
  chmod,
  mkdir,
  mkdtemp,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { ownedWrite, repairOwnedTree } from "./index";

async function scratch(): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), "shadowclone-storage-"));
}

async function modeOf(target: string): Promise<number> {
  return (await stat(target)).mode & 0o777;
}

test("owned write creates an owner-only file inside an owner-only directory", async () => {
  const root = await scratch();
  const filePath = path.join(root, "profile", "global", "identity.md");

  await ownedWrite({ path: filePath, content: "## rule\n" });

  expect(await modeOf(filePath)).toBe(0o600);
  expect(await modeOf(path.dirname(filePath))).toBe(0o700);
  expect(await Bun.file(filePath).text()).toBe("## rule\n");
});

test("owned write replaces existing content without loosening the mode", async () => {
  const root = await scratch();
  const filePath = path.join(root, "receipt.json");

  await ownedWrite({ path: filePath, content: "first" });
  await ownedWrite({ path: filePath, content: "second" });

  expect(await Bun.file(filePath).text()).toBe("second");
  expect(await modeOf(filePath)).toBe(0o600);
});

test("concurrent checkpoint writes create shared private directories", async () => {
  const root = await scratch();
  const files = ["first", "second", "third"].map((name) =>
    path.join(root, "distill", "checkpoints", `${name}.json`),
  );

  await Promise.all(
    files.map((filePath) => ownedWrite({ path: filePath, content: "{}" })),
  );

  for (const filePath of files) {
    expect(await Bun.file(filePath).text()).toBe("{}");
    expect(await modeOf(filePath)).toBe(0o600);
  }
});

test("owned write leaves no partial file behind", async () => {
  const root = await scratch();

  await ownedWrite({ path: path.join(root, "config.toml"), content: "a = 1" });

  const entries = [...new Bun.Glob("*").scanSync({ cwd: root, dot: true })];

  expect(entries).toEqual(["config.toml"]);
});

test("repair tightens a tree an older version left world readable", async () => {
  const root = await scratch();

  await mkdir(path.join(root, "runs", "abc"), { recursive: true });
  await writeFile(path.join(root, "runs", "abc", "receipt.json"), "{}");
  await writeFile(path.join(root, "config.toml"), "a = 1");
  await chmod(root, 0o755);
  await chmod(path.join(root, "runs"), 0o755);
  await chmod(path.join(root, "runs", "abc"), 0o755);
  await chmod(path.join(root, "runs", "abc", "receipt.json"), 0o644);
  await chmod(path.join(root, "config.toml"), 0o644);

  const summary = await repairOwnedTree(root);

  expect(summary.directories).toBe(3);
  expect(summary.files).toBe(2);
  expect(await modeOf(root)).toBe(0o700);
  expect(await modeOf(path.join(root, "runs", "abc"))).toBe(0o700);
  expect(await modeOf(path.join(root, "runs", "abc", "receipt.json"))).toBe(
    0o600,
  );
  expect(await modeOf(path.join(root, "config.toml"))).toBe(0o600);
});

test("repair reports nothing to change on an already tight tree", async () => {
  const root = await scratch();

  await ownedWrite({ path: path.join(root, "config.toml"), content: "a = 1" });
  await chmod(root, 0o700);

  const summary = await repairOwnedTree(root);

  expect(summary).toEqual({ directories: 0, files: 0, skipped: 0 });
});

test("repair skips a symbolic link instead of following it", async () => {
  const root = await scratch();
  const outside = await scratch();
  const target = path.join(outside, "secret");

  await writeFile(target, "secret");
  await chmod(target, 0o644);
  await symlink(target, path.join(root, "link"));

  const summary = await repairOwnedTree(root);

  expect(summary.skipped).toBe(1);
  expect(await modeOf(target)).toBe(0o644);
});

test("repair tolerates a tree that does not exist yet", async () => {
  const root = await scratch();

  const summary = await repairOwnedTree(path.join(root, "missing"));

  expect(summary).toEqual({ directories: 0, files: 0, skipped: 0 });
});
