import { expect, test } from "bun:test";
import { piProcessFixture } from "./pi.fixtures";
import { runPi, availablePiModels, requestPi } from "./pi";
import { createLearningExecution } from "./learning";

test("Pi uses provider-neutral no-tool calls with prepared input and keeps unknown cost", async () => {
  const fixture = await piProcessFixture();
  const previousPath = process.env.PATH;
  process.env.PATH = `${fixture.directory}:${previousPath}`;
  try {
    expect(await availablePiModels()).toEqual([{ id: "custom/fixture-model", name: "Synthetic provider" }]);
    const execution = createLearningExecution({ engine: "pi", runner: runPi, limits: { maximumCalls: 1, timeoutMilliseconds: 2000, maximumCostUsd: 1 } });
    const run = await execution.runner({ prompt: "Synthetic correction", cwd: "/synthetic/repository", model: "custom/fixture-model", execution: { purpose: "learning" }, outputSchema: { type: "object" } });
    expect(run.structured).toEqual({ accepted: true });
    expect(run.resolvedModel).toBe("custom/fixture-model");
    expect(run.costUsd).toBeNull();
    expect(run.actions).toEqual([]);
    const captured: unknown = await Bun.file(fixture.captured).json();
    expect(captured).toEqual([
      { id: "fixture-model", provider: "custom", name: "Synthetic provider" },
      { systemPrompt: expect.stringContaining("No Markdown"), messages: [{ role: "user", content: expect.stringContaining("Synthetic correction"), timestamp: expect.any(Number) }], tools: [] },
    ]);
    await expect(execution.runner({ prompt: "Second call", cwd: "/synthetic", execution: { purpose: "learning" } })).rejects.toThrow("call limit");
    await expect(runPi({ prompt: "Unavailable", cwd: "/synthetic", execution: { purpose: "learning" }, model: "custom/missing" })).rejects.toThrow("Pi model request failed");
  } finally { process.env.PATH = previousPath; await fixture.cleanup(); }
});

test("Pi rejects malformed JSON, tool calls, and oversized responses instead of treating them as learning", async () => {
  for (const scenario of [{ text: "Malformed response" }, { toolCall: true }, { text: "x".repeat(1_048_577) }]) {
    const fixture = await piProcessFixture(scenario);
    const previousPath = process.env.PATH;
    process.env.PATH = `${fixture.directory}:${previousPath}`;
    try {
      await expect(runPi({ prompt: "Synthetic", cwd: "/synthetic", execution: { purpose: "learning" }, model: "custom/fixture-model", outputSchema: {} })).rejects.toThrow();
    } finally { process.env.PATH = previousPath; await fixture.cleanup(); }
  }
});

test("Pi cancels a running model command and removes its prepared input", async () => {
  const fixture = await piProcessFixture({ hang: true });
  try {
    const controller = new AbortController();
    const cancelled = expect(requestPi({
      request: { prompt: "Synthetic" }, signal: AbortSignal.any([controller.signal, AbortSignal.timeout(2_000)]),
      environment: { ...process.env, PATH: `${fixture.directory}:${process.env.PATH}` },
    })).rejects.toThrow("cancelled");
    const deadline = Date.now() + 1_500;
    while (!await Bun.file(fixture.captured).exists() && Date.now() < deadline) await Bun.sleep(10);
    const started = await Bun.file(fixture.captured).exists();
    controller.abort();
    await cancelled;
    expect(started).toBeTrue();
    const requestPath = await Bun.file(fixture.requestLocation).text();
    expect(await Bun.file(requestPath).exists()).toBeFalse();
  } finally { await fixture.cleanup(); }
});

test("Pi refuses unsupported tool-using execution and unenforceable budgets before invoking its harness", async () => {
  await expect(requestPi({ request: { prompt: "Synthetic" }, environment: { SHADOWCLONE_PI_SOCKET: "/synthetic/socket" } })).rejects.toThrow("incomplete");
  await expect(runPi({ prompt: "Synthetic", cwd: "/synthetic", execution: { purpose: "evaluation" } })).rejects.toThrow("unavailable");
  await expect(runPi({ prompt: "Synthetic", cwd: "/synthetic", execution: { purpose: "learning" }, maxBudgetUsd: 1 })).rejects.toThrow("cannot enforce");
});
