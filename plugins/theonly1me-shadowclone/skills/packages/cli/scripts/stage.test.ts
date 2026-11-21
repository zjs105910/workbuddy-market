import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { stageCliPackage } from "./stage";

test("the stage fails and writes nothing when the build output is missing", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-stage-"));
  const packageDirectory = path.resolve(import.meta.dir, "..");
  const outputDirectory = path.join(root, "package");

  try {
    await mkdir(path.join(root, "workspace"));

    await expect(
      stageCliPackage({
        packageDirectory,
        distDirectory: path.join(root, "missing-dist"),
        workspaceRoot: path.join(root, "workspace"),
        outputDirectory,
      }),
    ).rejects.toThrow("these inputs are missing: dist (");
    expect(await Bun.file(path.join(outputDirectory, "package.json")).exists()).toBeFalse();
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
