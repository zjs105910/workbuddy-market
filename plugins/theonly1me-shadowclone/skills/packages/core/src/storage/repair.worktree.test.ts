import { expect, test } from "bun:test";
import { chmod, mkdir, mkdtemp, rm, stat, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { repairOwnedTree } from "./index";

test("permission repair preserves executable checkout files", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-repair-"));

  try {
    const checkout = path.join(root, "worktrees", "run");

    await mkdir(checkout, { recursive: true });

    const script = path.join(checkout, "verify");

    await writeFile(script, "exit 0\n");
    await chmod(script, 0o755);
    await repairOwnedTree(root);

    expect((await stat(script)).mode & 0o777).toBe(0o755);
    expect((await stat(path.join(root, "worktrees"))).mode & 0o777).toBe(0o700);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
