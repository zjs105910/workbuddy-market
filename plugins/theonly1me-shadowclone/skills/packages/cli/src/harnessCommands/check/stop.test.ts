import { expect, test } from "bun:test";
import path from "node:path";
import { harnessInitCommand } from "../../harness";
import { harnessCheckCommand } from "../../harnessCheck";
import { acceptAll } from "@shadowclone/harness/testing";
import { stopHookCommand } from "@shadowclone/harness";
import { checkedRepository } from "./testRepository";

function stopInput(options: {
  readonly cwd: string;
  readonly active: boolean;
}): string {
  return JSON.stringify({
    session_id: "session",
    hook_event_name: "Stop",
    cwd: options.cwd,
    stop_hook_active: options.active,
  });
}

test("the Claude stop format blocks with exit 2 and a remediation list, but never twice in a row", async () => {
  const setup = await checkedRepository();

  await Bun.write(
    path.join(setup.root, "src/commented.ts"),
    "export const answer = 42;\n// explains the answer\n",
  );

  const written: string[] = [];
  const write = async (streams: {
    readonly stdout: string;
    readonly stderr: string;
  }) => {
    written.push(streams.stderr);
  };

  expect(
    await harnessCheckCommand({
      changed: true,
      format: "claude-stop",
      stdin: stopInput({ cwd: path.join(setup.root, "src"), active: false }),
      write,
    }),
  ).toBe(2);
  expect(written.join("")).toContain(
    "- src/commented.ts:2 no-comments: Delete the comment.",
  );
  expect(
    await harnessCheckCommand({
      changed: true,
      format: "claude-stop",
      stdin: stopInput({ cwd: setup.root, active: true }),
      write,
    }),
  ).toBe(0);
});

test("the Claude stop format stays silent when the change is clean", async () => {
  const setup = await checkedRepository();
  const written: string[] = [];
  const write = async (streams: {
    readonly stdout: string;
    readonly stderr: string;
  }) => {
    written.push(streams.stdout, streams.stderr);
  };

  expect(
    await harnessCheckCommand({
      changed: true,
      format: "claude-stop",
      stdin: stopInput({ cwd: setup.root, active: false }),
      write,
    }),
  ).toBe(0);
  expect(written.join("")).toBe("");
});

test("--enforce-claude adds the Stop hook once and keeps existing settings", async () => {
  const setup = await checkedRepository({ enforceClaude: true });
  const settingsPath = path.join(setup.root, ".claude/settings.local.json");
  const settings = JSON.parse(await Bun.file(settingsPath).text());

  expect(settings.hooks.Stop).toEqual([
    { hooks: [{ type: "command", command: stopHookCommand, timeout: 60 }] },
  ]);

  await Bun.write(
    settingsPath,
    JSON.stringify({
      permissions: { allow: ["Bash(bun test:*)"] },
      hooks: settings.hooks,
    }),
  );
  await harnessInitCommand({
    apply: true,
    personal: true,
    skills: [],
    enforceClaude: true,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    ask: acceptAll,
    writeLine: () => undefined,
  });

  const merged = JSON.parse(await Bun.file(settingsPath).text());

  expect(merged.hooks.Stop).toHaveLength(1);
  expect(merged.permissions).toEqual({ allow: ["Bash(bun test:*)"] });

  const manifest = JSON.parse(
    await Bun.file(path.join(setup.root, ".shadowclone/harness.json")).text(),
  );

  expect(Object.keys(manifest.artifacts)).not.toContain(
    ".claude/settings.local.json",
  );
});
