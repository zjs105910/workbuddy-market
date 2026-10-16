import { chmod, lstat, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { expect, test } from "bun:test";
import { redactedFailure, runClaudeCode } from "./claudeCode";
import { missingClaudeSandboxTools } from "./claudeIsolation";
import { parseClaudeStream } from "./parseClaude";

test("Linux Claude learning names missing sandbox commands before a run", () => {
  expect(missingClaudeSandboxTools({
    platform: "linux",
    which: (name) => name === "bwrap" ? "/usr/bin/bwrap" : null,
  })).toEqual(["socat"]);
  expect(missingClaudeSandboxTools({ platform: "darwin", which: () => null })).toEqual([]);
});

test("a long minified provider diagnostic is not printed", () => {
  const message = redactedFailure({
    run: parseClaudeStream({ stream: "", fallbackSessionId: "synthetic" }),
    stderr: "minifiedSource".repeat(400),
    exitCode: 1,
  });

  expect(message).toContain("too large to display");
  expect(message).not.toContain("minifiedSource");
});

async function withStub(options: {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
  readonly run: (cwd: string) => Promise<void>;
}): Promise<void> {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-engine-"),
  );

  await Bun.write(path.join(directory, "stdout.txt"), options.stdout);
  await Bun.write(path.join(directory, "stderr.txt"), options.stderr);

  const executable = path.join(directory, "claude");

  await Bun.write(
    executable,
    [
      "#!/bin/sh",
      "cat > /dev/null",
      `cat "${directory}/stdout.txt"`,
      `cat "${directory}/stderr.txt" >&2`,
      `exit ${options.exitCode}`,
    ].join("\n"),
  );
  await chmod(executable, 0o755);

  const originalPath = process.env.PATH ?? "";

  process.env.PATH = `${directory}:${originalPath}`;

  try {
    await options.run(directory);
  } finally {
    process.env.PATH = originalPath;
    await rm(directory, { recursive: true, force: true });
  }
}

test("redacts stderr from a failing engine process", async () => {
  await withStub({
    stdout: "",
    stderr: "auth failed for sk-abcdefghijklmnop at /Users/dev/work/acme",
    exitCode: 1,
    run: async (cwd) => {
      const run = await runClaudeCode({
        prompt: "hello",
        cwd,
        execution: { purpose: "learning" },
        allowedTools: [],
        permissionMode: "dontAsk",
      });

      expect(run.isError).toBeTrue();
      expect(run.errorMessage).not.toContain("sk-abcdefghijklmnop");
      expect(run.errorMessage).not.toContain("/Users/dev/work/acme");
      expect(run.errorMessage).toContain("[redacted:llm-api-key]");
    },
  });
});

test("redacts a rejected command message on a zero exit code", async () => {
  await withStub({
    stdout: JSON.stringify({
      type: "result",
      is_error: false,
      num_turns: 0,
      session_id: "stub-session",
      result: [
        "/plan isn't available in this environment.",
        ("token " + ["ghp", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_")),
      ].join(" "),
    }),
    stderr: "",
    exitCode: 0,
    run: async (cwd) => {
      const run = await runClaudeCode({
        prompt: "hello",
        cwd,
        execution: { purpose: "learning" },
        allowedTools: [],
        permissionMode: "dontAsk",
      });

      expect(run.isError).toBeTrue();
      expect(run.errorMessage).not.toContain(
        ["ghp", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_"),
      );
      expect(run.errorMessage).toContain("[redacted:github-token]");
    },
  });
});

test("creates an isolated runtime directory before evaluation", async () => {
  await withStub({
    stdout: "",
    stderr: "",
    exitCode: 0,
    run: async (cwd) => {
      await runClaudeCode({
        prompt: "hello",
        cwd,
        execution: { purpose: "evaluation", blockedPaths: [] },
        allowedTools: [],
        permissionMode: "dontAsk",
      });

      expect(
        (await lstat(path.join(cwd, ".eval-runtime"))).isDirectory(),
      ).toBeTrue();
    },
  });
});
