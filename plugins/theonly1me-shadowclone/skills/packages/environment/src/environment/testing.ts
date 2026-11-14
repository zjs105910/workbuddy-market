import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import {
  createLearningExecution,
  type EngineRun,
  type EngineRunner,
} from "@shadowclone/agents";
import { integrationFixture } from "@shadowclone/core/testing";
import { fixtureSkill } from "@shadowclone/skills/testing";
import { configureSkillMaintenance } from "@shadowclone/skills";

export async function skillFixture(
  options: {
    readonly thirdParty?: boolean;
    readonly scope?: "global" | "repository";
  } = {},
) {
  const setup = await integrationFixture();
  const scope = options.scope ?? "global";

  const directory = options.thirdParty
    ? path.join(
        setup.home,
        ".codex/plugins/cache/publisher/plugin/1.0/skills/typed-changes",
      )
    : path.join(
        scope === "global" ? setup.home : setup.cwd,
        ".claude/skills/typed-changes",
      );

  const filePath = path.join(directory, "SKILL.md");
  const original = fixtureSkill();

  await Bun.write(filePath, original);
  await writeConfig({
    configPath: setup.paths.configFile,
    config: {
      ...defaultConfig,
      distillation: { deep: true, automatic: false },
    },
  });
  await configureSkillMaintenance({ ...setup, scope });

  return { ...setup, filePath, directory, original };
}

export function skillEngineRun(structured: unknown): EngineRun {
  return {
    engine: "claude-code",
    sessionId: "internal-skill-assessment",
    transcriptPath: null,
    text: "",
    structured,
    costUsd: 0.01,
    durationMs: 1,
    turns: 1,
    isError: false,
    permissionDenials: [],
    actions: [],
    errorMessage: null,
  };
}

export function skillExecution(
  options: {
    readonly passage?: string;
    readonly description?: string;
    readonly onPrompt?: (prompt: string) => void;
    readonly maximumCalls?: number;
    readonly verify?: boolean;
  } = {},
) {
  const runner: EngineRunner = (run) => {
    options.onPrompt?.(run.prompt);

    const tokens = [
      ...new Set(
        [...run.prompt.matchAll(/"token":"(skill-\d+)"/g)].flatMap((match) =>
          match[1] ? [match[1]] : [],
        ),
      ),
    ];

    return Promise.resolve(
      skillEngineRun({
        assessments: tokens.map((token) => ({
          token,
          decision: options.verify ? "needs-verification" : "update",
          description: options.description ?? "",
          passages: [options.passage ?? "Use complete names."],
          findings: options.verify ? ["technical-verification"] : [],
        })),
      }),
    );
  };

  return createLearningExecution({
    engine: "claude-code",
    runner,
    limits: {
      maximumCalls: options.maximumCalls ?? 20,
      timeoutMilliseconds: 300_000,
      maximumCostUsd: 2,
    },
  });
}
