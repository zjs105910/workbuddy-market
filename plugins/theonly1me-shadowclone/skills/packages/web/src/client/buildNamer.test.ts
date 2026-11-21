import { expect, test } from "bun:test";
import type { BuildNameResult } from "../buildNameProtocol";
import { createBuildNamer, namingDelayMilliseconds, type NamerState } from "./buildNamer";
import type { BuildInput } from "@shadowclone/environment/browser";

const input: BuildInput = { scope: "global", choices: { "tests-that-catch-bugs": true }, edits: {}, custom: [] };

function named(title: string): BuildNameResult {
  return {
    name: {
      title,
      profile: "You test first. You read the real output.",
      abilities: [{ skill: "Tests that catch bugs", text: "Proves each test fails without the fix." }],
      tradeoff: "Slower first drafts.",
    },
    destination: "claude-code using haiku",
  };
}

function harness(options: { readonly fetchName?: (signal: AbortSignal) => Promise<BuildNameResult> } = {}) {
  const timers = new Map<number, { readonly run: () => void; readonly delayMilliseconds: number }>();
  const states: NamerState["status"][] = [];
  const requests: AbortSignal[] = [];
  let nextHandle = 0;
  const namer = createBuildNamer({
    schedule: (timer) => {
      nextHandle += 1;
      timers.set(nextHandle, timer);

      return nextHandle;
    },
    cancel: (handle) => timers.delete(handle),
    fetchName: ({ signal }) => {
      requests.push(signal);

      return options.fetchName ? options.fetchName(signal) : Promise.resolve(named(`Build ${requests.length}`));
    },
    onChange: (state) => states.push(state.status),
  });
  const fire = async (): Promise<void> => {
    const pending = [...timers.values()];

    timers.clear();

    for (const timer of pending) timer.run();

    await Bun.sleep(0);
  };

  return { namer, timers, states, requests, fire };
}

test("names the build once, 5 seconds after the last change", async () => {
  const { namer, timers, requests, fire } = harness();

  namer.update({ key: "a", input, enabled: true, changed: true });
  namer.update({ key: "a,b", input, enabled: true, changed: true });
  namer.update({ key: "a,b,c", input, enabled: true, changed: true });

  expect([...timers.values()].map((timer) => timer.delayMilliseconds)).toEqual([namingDelayMilliseconds]);
  expect(namer.state().status).toBe("waiting");
  expect(requests).toHaveLength(0);

  await fire();

  expect(requests).toHaveLength(1);
  expect(namer.state()).toEqual({ status: "ready", result: named("Build 1") });
});

test("a selection that was named before shows its cached name with no request", async () => {
  const { namer, requests, fire } = harness();

  namer.update({ key: "a", input, enabled: true, changed: true });
  await fire();
  namer.update({ key: "a,b", input, enabled: true, changed: true });
  await fire();
  namer.update({ key: "a", input, enabled: true, changed: true });

  expect(requests).toHaveLength(2);
  expect(namer.state()).toEqual({ status: "ready", result: named("Build 1") });
});

test("a change during a request cancels it and ignores its answer", async () => {
  let release: (result: BuildNameResult) => void = () => undefined;
  const { namer, requests, fire } = harness({
    fetchName: () => new Promise((resolve) => (release = resolve)),
  });

  namer.update({ key: "a", input, enabled: true, changed: true });
  await fire();
  namer.update({ key: "a,b", input, enabled: true, changed: true });
  release(named("Stale"));
  await Bun.sleep(0);

  expect(requests[0]?.aborted).toBeTrue();
  expect(namer.state().status).toBe("waiting");
});

test("a failure shows on the sheet, and Retry asks again at once", async () => {
  let attempts = 0;
  const { namer, fire } = harness({
    fetchName: () => {
      attempts += 1;

      return attempts === 1 ? Promise.reject(new Error("claude-code could not name the build")) : Promise.resolve(named("Recovered"));
    },
  });

  namer.update({ key: "a", input, enabled: true, changed: true });
  await fire();

  expect(namer.state()).toEqual({ status: "failed", error: "claude-code could not name the build" });

  namer.retry();
  await Bun.sleep(0);

  expect(namer.state()).toEqual({ status: "ready", result: named("Recovered") });
});

test("the off switch and an empty build make no request", async () => {
  const { namer, timers, requests, fire } = harness();

  namer.update({ key: "a", input, enabled: false, changed: true });
  namer.update({ key: null, input, enabled: true, changed: true });
  await fire();

  expect(timers.size).toBe(0);
  expect(requests).toHaveLength(0);
  expect(namer.state().status).toBe("empty");

  namer.update({ key: "a", input, enabled: false, changed: true });

  expect(namer.state().status).toBe("off");

  namer.update({ key: "a", input, enabled: true, changed: true });

  expect(namer.state().status).toBe("waiting");
});

test("opening a saved build makes no request until the user names it or changes it", async () => {
  const { namer, timers, requests, fire } = harness();

  namer.update({ key: "a", input, enabled: true, changed: false });
  await fire();

  expect(timers.size).toBe(0);
  expect(requests).toHaveLength(0);
  expect(namer.state().status).toBe("unnamed");

  namer.retry();
  await Bun.sleep(0);

  expect(namer.state()).toEqual({ status: "ready", result: named("Build 1") });
});
