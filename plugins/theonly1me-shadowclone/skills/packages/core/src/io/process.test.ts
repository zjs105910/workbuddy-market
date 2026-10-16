import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { runProcess } from "./process";

test("a noisy process is terminated before output can grow without bound", async () => {
  await expect(
    runProcess({
      arguments: [
        process.execPath,
        "-e",
        "while (true) process.stdout.write('x'.repeat(4096))",
      ],
      cwd: os.tmpdir(),
      environment: {},
      maximumOutputBytes: 8192,
      timeoutMilliseconds: 2000,
    }),
  ).rejects.toThrow("output limit");
});

test("timeout kills descendants before they can write a later sentinel", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-process-"),
  );

  try {
    await expect(
      runProcess({
        arguments: [
          "/bin/sh",
          "-c",
          "(sleep 0.4; echo escaped > sentinel) & wait",
        ],
        cwd: directory,
        environment: { PATH: "/usr/bin:/bin" },
        timeoutMilliseconds: 50,
      }),
    ).rejects.toThrow("timed out");
    await Bun.sleep(500);

    expect(
      await Bun.file(path.join(directory, "sentinel")).exists(),
    ).toBeFalse();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
