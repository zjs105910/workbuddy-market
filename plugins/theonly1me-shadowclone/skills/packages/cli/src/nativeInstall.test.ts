import { expect, spyOn, test } from "bun:test";
import { UnsafeDestinationError } from "@shadowclone/core";
import { HiddenInstructionsError } from "@shadowclone/environment";
import { installNativeCommand } from "./native";
import { describeSkippedAgent } from "./skippedAgents";

type Install = NonNullable<Parameters<typeof installNativeCommand>[0]["install"]>;

function installer(blocked: string) {
  const attempted: string[] = [];
  const install: Install = async (options) => {
    attempted.push(options.agent);

    if (options.agent === blocked) {
      throw new UnsafeDestinationError(
        "/home/sample/.codex/AGENTS.md",
        "/home/sample/.agents/AGENTS.md",
      );
    }

    return {};
  };

  return { attempted, install };
}

const options = {
  agents: ["claude-code", "codex", "cursor"] as const,
  scope: "global" as const,
  subagent: false,
  autoDelegate: false,
};

test("setup skips an agent whose file is a symbolic link and installs the rest", async () => {
  const log = spyOn(console, "log").mockImplementation(() => undefined);
  const fixture = installer("codex");

  try {
    const result = await installNativeCommand({
      ...options,
      skipUnsafeDestinations: true,
      install: fixture.install,
    });

    const lines = log.mock.calls.map((call) => String(call[0]));

    expect(fixture.attempted).toEqual(["claude-code", "codex", "cursor"]);
    expect(lines).toContain("Installed claude-code main-agent guidance (global).");
    expect(lines).toContain("Installed cursor main-agent guidance (global).");
    expect(lines.some((line) => line.includes("codex"))).toBeFalse();
    expect(result.skipped).toEqual([
      {
        agent: "codex",
        kind: "link",
        path: "/home/sample/.codex/AGENTS.md",
        target: "/home/sample/.agents/AGENTS.md",
      },
    ]);
  } finally {
    log.mockRestore();
  }
});

test("an explicit install still fails on a symbolic link", async () => {
  const fixture = installer("codex");

  await expect(
    installNativeCommand({ ...options, agents: ["codex"], install: fixture.install }),
  ).rejects.toBeInstanceOf(UnsafeDestinationError);
});

test("an install skips codex when its override would hide the team file, and installs the rest", async () => {
  const log = spyOn(console, "log").mockImplementation(() => undefined);
  const attempted: string[] = [];
  const install: Install = async (installOptions) => {
    attempted.push(installOptions.agent);

    if (installOptions.agent === "codex") {
      throw new HiddenInstructionsError({
        override: "/work/repo/AGENTS.override.md",
        hidden: "/work/repo/AGENTS.md",
        installed: false,
      });
    }

    return {};
  };

  try {
    const result = await installNativeCommand({ ...options, scope: "repository", install });

    expect(attempted).toEqual(["claude-code", "codex", "cursor"]);
    expect(result.skipped.map(describeSkippedAgent)).toEqual([
      "Not installed for codex: /work/repo/AGENTS.override.md would hide the team file /work/repo/AGENTS.md, because Codex reads one instruction file in each folder. Use shadowclone install --agent codex --global instead.",
    ]);
  } finally {
    log.mockRestore();
  }
});

test("an override that Shadowclone created tells the user how to remove it", () => {
  expect(
    describeSkippedAgent({
      agent: "codex",
      kind: "hidden",
      override: "/work/repo/AGENTS.override.md",
      hidden: "/work/repo/AGENTS.md",
      installed: true,
    }),
  ).toBe(
    "Not installed for codex: /work/repo/AGENTS.override.md, which Shadowclone created, hides the team file /work/repo/AGENTS.md, because Codex reads one instruction file in each folder. Run shadowclone uninstall --agent codex --local to remove it, and use shadowclone install --agent codex --global instead.",
  );
});
