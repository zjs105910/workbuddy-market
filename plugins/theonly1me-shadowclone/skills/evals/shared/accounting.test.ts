import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { evaluationBudget } from "./accounting";

test("total allowance is shared and survives resume", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-budget-"),
  );

  try {
    const options = { directory, maximumCalls: 10, limitUsd: 2 };
    const first = await evaluationBudget({ ...options, resume: false });

    expect(await first.reserve()).toBe(2);

    await first.settle(1.25);

    const resumed = await evaluationBudget({ ...options, resume: true });

    expect(await resumed.reserve()).toBe(0.75);

    await resumed.settle(0.75);

    await expect(resumed.reserve()).rejects.toThrow("total budget");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("unknown interrupted spend and changed resume limits cannot reset the budget", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-interrupted-"),
  );

  try {
    const options = { directory, maximumCalls: 10, limitUsd: 2 };
    const first = await evaluationBudget({ ...options, resume: false });

    await first.reserve();

    await expect(first.reserve()).rejects.toThrow("serialized");

    const resumed = await evaluationBudget({ ...options, resume: true });

    await expect(resumed.reserve()).rejects.toThrow("cost unknown");
    await expect(
      evaluationBudget({ ...options, resume: true, limitUsd: 3 }),
    ).rejects.toThrow("original total");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("engines without reported costs retain their attempted-call ceiling across resume", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-call-limit-"),
  );

  try {
    const options = { directory, maximumCalls: 1 };
    const first = await evaluationBudget({ ...options, resume: false });

    expect(await first.reserve()).toBeUndefined();

    await first.settle(null);

    const resumed = await evaluationBudget({ ...options, resume: true });

    await expect(resumed.reserve()).rejects.toThrow("invocation limit");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
