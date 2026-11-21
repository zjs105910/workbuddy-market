import { expect, test } from "bun:test";
import { chmod, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { runProcess } from "@shadowclone/core";
import { runCodex } from "./codex";
import { evaluationCommand } from "./evaluationIsolation";

async function withCodexStub(options: {
  readonly script: string;
  readonly run: (directory: string) => Promise<void>;
}): Promise<void> {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-codex-process-"),
  );
  const executable = path.join(directory, "codex");

  await Bun.write(executable, `#!/bin/sh\ncat >/dev/null\n${options.script}\n`);
  await chmod(executable, 0o755);

  const previousPath = process.env.PATH;
  const previousCodexHome = process.env.CODEX_HOME;

  process.env.PATH = `${directory}:${previousPath ?? ""}`;
  process.env.CODEX_HOME = path.join(directory, "source-home");

  try {
    await options.run(directory);
  } finally {
    if (previousPath === undefined) {
      delete process.env.PATH;
    } else {
      process.env.PATH = previousPath;
    }

    if (previousCodexHome === undefined) {
      delete process.env.CODEX_HOME;
    } else {
      process.env.CODEX_HOME = previousCodexHome;
    }

    await rm(directory, { recursive: true, force: true });
  }
}

test("Codex stops a provider process that exceeds the output limit", async () => {
  await withCodexStub({
    script: "head -c 18000000 /dev/zero",
    run: async (cwd) => {
      await expect(
        runCodex({
          prompt: "Synthetic learning input",
          cwd,
          execution: { purpose: "learning" },
          allowedTools: [],
          permissionMode: "dontAsk",
        }),
      ).rejects.toThrow("Process output limit exceeded");
    },
  });
});

test("a Codex judge can write its isolated runtime state", async () => {
  await withCodexStub({
    script:
      'touch "$CODEX_HOME/runtime-state" || exit 1\nprintf \'%s\\n\' \'{"type":"turn.completed"}\'',
    run: async (cwd) => {
      const run = {
        prompt: "Synthetic judging input",
        cwd,
        execution: { purpose: "evaluation" as const, access: "read" as const },
        allowedTools: [],
      };
      const probe = await runProcess({
        arguments: evaluationCommand({ arguments: ["/usr/bin/true"], run }),
        cwd,
        environment: { PATH: process.env.PATH },
      });

      if (probe.exitCode !== 0) {
        if (process.env.CI) {
          throw new Error("Evaluation sandbox is unavailable");
        }

        console.log(
          "Codex sandbox check requires execution outside the host sandbox.",
        );

        return;
      }

      expect((await runCodex(run)).isError).toBeFalse();
    },
  });
});
