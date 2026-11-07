import { expect, test } from "bun:test";
import { buildFixture, buildInput } from "@shadowclone/builds/testing";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { buildClaudeArguments, buildCodexArguments, fastSystemPrompt } from "@shadowclone/agents";
import type { EngineId, EngineRunOptions } from "@shadowclone/agents";
import { createBuildNames } from "./buildNames";
import { generationResult } from "./fixtures";
import { generationEngine } from "./generationEngine";

const dash = String.fromCharCode(0x2014);

function answer(overrides: Record<string, unknown> = {}) {
  return {
    title: "Ledger Sentinel",
    profile: `You prove every fix ${dash} you show the failing test first. You keep scope tight.`,
    abilities: [{ skill: "Tests that catch bugs", text: "Proves each test fails without the fix." }],
    tradeoff: "First drafts take longer.",
    ...overrides,
  };
}

async function namer(options: { readonly engine?: EngineId; readonly structured?: unknown; readonly isError?: boolean } = {}) {
  const context = await buildFixture();
  const runs: EngineRunOptions[] = [];
  const names = createBuildNames({
    ...context,
    random: () => 0,
    engine: {
      engine: options.engine ?? "claude-code",
      runner: async (run) => {
        runs.push(run);

        return { ...generationResult(options.structured ?? answer()), engine: options.engine ?? "claude-code", isError: options.isError ?? false, errorMessage: options.isError ? "model not found" : null };
      },
    },
  });

  return { context, runs, names };
}

const input = buildInput({ choices: { "tests-that-catch-bugs": true } });

test("Claude Code names the build with haiku at low effort, thinking off, and a short system prompt under the fast limits", async () => {
  const { runs, names } = await namer();
  const result = await names({ input });
  const [run] = runs;

  if (!run) throw new Error("The model was not called");

  const arguments_ = buildClaudeArguments({ sessionId: "00000000-0000-4000-8000-000000000000", run });

  expect(arguments_.join(" ")).toContain("--model haiku --effort low");
  expect(arguments_.join(" ")).toContain("--max-budget-usd 0.05");
  expect(arguments_.join(" ")).toContain('"env":{"MAX_THINKING_TOKENS":"0"}');
  expect(arguments_[arguments_.indexOf("--system-prompt") + 1]).toBe(fastSystemPrompt);
  expect(result.destination).toBe("claude-code using haiku");
});

test("Codex names the build with gpt-6-luna at low effort", async () => {
  const { runs, names } = await namer({ engine: "codex" });

  await names({ input });

  const [run] = runs;

  if (!run) throw new Error("The model was not called");

  const arguments_ = buildCodexArguments({ run }).join(" ");

  expect(arguments_).toContain("--model gpt-6-luna");
  expect(arguments_).toContain('model_reasoning_effort="low"');
});

test("the saved tier keeps the saved model, sets no effort, and keeps thinking and the default system prompt", async () => {
  const { context, runs } = await namer();

  await writeConfig({
    configPath: context.paths.configFile,
    config: { ...defaultConfig, distillation: { deep: true, engine: "claude-code", model: "synthetic-saved" } },
  });

  const saved = await generationEngine({
    ...context,
    engine: {
      engine: "claude-code",
      runner: async (run) => {
        runs.push(run);

        return generationResult(answer());
      },
    },
  });

  await saved.runner({ prompt: "p", cwd: context.cwd, execution: { purpose: "learning" } });

  expect(runs.map((run) => [run.model, run.reasoningEffort, run.thinking, run.systemPrompt])).toEqual([
    ["synthetic-saved", undefined, undefined, undefined],
  ]);
});

test("the request sends only titles and summaries, and a repeat selection uses the cache", async () => {
  const { runs, names } = await namer();
  const first = await names({ input });
  const second = await names({ input });

  expect(runs).toHaveLength(1);
  expect(second).toEqual(first);
  expect(runs[0]?.prompt).toContain('"title": "Tests that catch bugs"');
  expect(runs[0]?.prompt).not.toContain("## Gates");
  expect(runs[0]?.prompt).toContain("Never use these words in the title: Pathfinder");
  expect(first.name.profile).not.toContain(dash);
});

test("a name that cites a skill that is not equipped fails loudly", async () => {
  const { names } = await namer({
    structured: answer({ abilities: [{ skill: "Deploy on Fridays", text: "Ships anything." }] }),
  });

  expect(names({ input })).rejects.toThrow("The model named a skill that is not equipped: Deploy on Fridays");
});

test("a banned default title and a provider error both fail loudly", async () => {
  const banned = await namer({ structured: answer({ title: "The Testing Pathfinder" }) });
  const failed = await namer({ isError: true });

  expect(banned.names({ input })).rejects.toThrow('The model used the banned title word "Pathfinder"');
  expect(failed.names({ input })).rejects.toThrow("claude-code using haiku could not name the build: model not found");
});
