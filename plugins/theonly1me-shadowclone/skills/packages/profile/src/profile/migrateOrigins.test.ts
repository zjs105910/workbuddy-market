import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { migrateOriginProfiles } from "./migrateOrigins";
import { originDirectoryName } from "@shadowclone/sessions";

test("migrates an unambiguous scope and its state without merging ambiguous owners", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-origin-migration-"),
  );

  try {
    const legacy = path.join(directory, "org", "github.com--example");
    const ambiguous = path.join(directory, "org", "example.com--team--sub");

    await mkdir(legacy, { recursive: true });
    await mkdir(ambiguous, { recursive: true });
    await Bun.write(
      path.join(legacy, "workflow.md"),
      "## Preserved guidance\n",
    );
    await Bun.write(
      path.join(directory, ".generated"),
      '{"relativePath":"org/github.com--example/workflow.md","key":"one"}\n',
    );

    const result = await migrateOriginProfiles(directory);
    const target = originDirectoryName("github.com/example");

    expect(result).toEqual({ migrated: 1, isolated: 1 });
    expect(
      await Bun.file(path.join(directory, "org", target, "workflow.md")).text(),
    ).toBe("## Preserved guidance\n");
    expect(await Bun.file(path.join(directory, ".generated")).text()).toContain(
      `org/${target}/workflow.md`,
    );
    expect((await migrateOriginProfiles(directory)).migrated).toBe(0);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("finishes interrupted state updates after the scope directory was moved", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-origin-recovery-"),
  );

  try {
    const target = originDirectoryName("github.com/example");

    await mkdir(path.join(directory, "org", target), { recursive: true });
    await Bun.write(
      path.join(directory, ".origin-migration"),
      "github.com--example",
    );
    await Bun.write(
      path.join(directory, ".rejected"),
      '{"relativePath":"org/github.com--example/workflow.md","key":"one"}\n',
    );

    expect((await migrateOriginProfiles(directory)).migrated).toBe(1);
    expect(await Bun.file(path.join(directory, ".rejected")).text()).toContain(
      `org/${target}/workflow.md`,
    );
    expect(
      await Bun.file(path.join(directory, ".origin-migration")).exists(),
    ).toBeFalse();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
