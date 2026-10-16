import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { runProcess } from "@shadowclone/core";
import { evaluationCommand } from "./index";

test("evaluation retains permitted host reads but cannot write outside its workspace", async () => {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-eval-writes-"),
  );

  try {
    const directory = path.join(root, "workspace");
    const control = path.join(root, "control");
    const outside = path.join(root, "host-file");

    await mkdir(directory);
    await mkdir(control);
    await writeFile(outside, "host-fixture");
    await writeFile(path.join(control, "state"), "control-fixture");

    const execute = (arguments_: readonly string[]) =>
      runProcess({
        arguments: evaluationCommand({
          arguments: arguments_,
          run: {
            prompt: "",
            cwd: directory,
            execution: { purpose: "evaluation", blockedPaths: [control] },
          },
        }),
        cwd: directory,
        environment: { PATH: process.env.PATH },
        timeoutMilliseconds: 5000,
      });
    const probe = await execute(["/usr/bin/true"]).catch(() => null);

    if (probe === null || probe.exitCode !== 0) {
      if (process.env.CI) {
        throw new Error(
          `Evaluation sandbox unavailable: ${probe?.stderr.trim() || "process did not start"}`,
        );
      }

      console.log(
        "Evaluation sandbox unavailable inside the current host sandbox; run the targeted check outside it.",
      );

      return;
    }

    const result = await execute([
      "/bin/sh",
      "-c",
      'echo allowed > changed; cat "$1" > observed; cat "$2" > hidden; echo escaped > "$1"',
      "fixture",
      outside,
      path.join(control, "state"),
    ]);

    expect(result.exitCode).not.toBe(0);
    expect(await Bun.file(path.join(directory, "changed")).text()).toBe(
      "allowed\n",
    );
    expect(await Bun.file(path.join(directory, "observed")).text()).toBe(
      "host-fixture",
    );
    expect(await Bun.file(path.join(directory, "hidden")).text()).toBe("");
    expect(await Bun.file(outside).text()).toBe("host-fixture");
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
