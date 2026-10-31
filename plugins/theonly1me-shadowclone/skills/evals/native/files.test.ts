import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, symlink, lstat } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { requirePrivateDirectory, writeFrozenFile, treeFingerprint } from "./files";
import { validateNativeFile } from "./workspace";

test("private evidence cannot be written anywhere inside a checkout", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "native-storage-"));
  try {
    await mkdir(path.join(root, ".git"));
    await expect(requirePrivateDirectory(path.join(root, "ignored", "receipts"))).rejects.toThrow("inside a repository");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("frozen context cannot escape through a parent link", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "native-context-"));
  try {
    const directory = path.join(root, "snapshot");
    const outside = path.join(root, "outside");
    await mkdir(directory);
    await mkdir(outside);
    await symlink(outside, path.join(directory, "linked"));
    await expect(writeFrozenFile({ directory, file: { path: "linked/new/secret", content: "synthetic", encoding: "utf8", mode: 384 } })).rejects.toThrow("escapes");
    expect(await lstat(path.join(outside, "new")).catch(() => null)).toBeNull();
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("template fingerprints change when source content changes", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "native-fingerprint-"));
  try {
    await Bun.write(path.join(root, "example.ts"), "export const value = 1;\n");
    const previous = await treeFingerprint(root);
    await Bun.write(path.join(root, "example.ts"), "export const value = 2;\n");
    expect(await treeFingerprint(root)).not.toBe(previous);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("guidance cannot replace authentication or runtime configuration", () => {
  for (const filePath of [".codex/auth.json", ".claude/settings.json", "package.json"]) {
    expect(() => validateNativeFile({ root: "home", path: filePath, content: "", encoding: "utf8", mode: 384 })).toThrow("non-guidance");
  }
});
