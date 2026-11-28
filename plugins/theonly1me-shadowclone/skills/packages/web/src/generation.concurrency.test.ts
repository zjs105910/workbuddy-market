import { expect, test } from "bun:test";
import { buildFixture } from "@shadowclone/builds/testing";
import { generationResult, syntheticBrief, syntheticSkill } from "./fixtures";
import { createSkillDrafts } from "./skillDrafts";

test("concurrent submissions share one provider call and cancellation reaches it", async () => {
  const context = await buildFixture();
  const started = Promise.withResolvers<void>();
  let calls = 0;
  let canceled = false;
  const drafts = createSkillDrafts({
    ...context,
    engine: {
      engine: "claude-code",
      runner: async (run) => {
        calls += 1;
        started.resolve();

        await new Promise<void>((resolve, reject) => {
          const abort = () => {
            canceled = true;
            reject(new Error("Synthetic provider canceled"));
          };

          if (run.signal?.aborted) {
            abort();
          } else if (run.signal) {
            run.signal.addEventListener("abort", abort, { once: true });
          } else {
            resolve();
          }
        });

        return generationResult(syntheticSkill);
      },
    },
  });
  const review = await drafts.preview(syntheticBrief);
  const controller = new AbortController();
  const generating = drafts.generate({
    id: review.id,
    signal: controller.signal,
  });

  await started.promise;
  await expect(drafts.generate({ id: review.id })).rejects.toThrow(
    "Review a fresh",
  );
  await expect(drafts.preview(syntheticBrief)).rejects.toThrow(
    "Wait for the current",
  );
  controller.abort();

  await expect(generating).rejects.toThrow("Synthetic provider canceled");
  expect(canceled).toBe(true);
  expect(calls).toBe(1);
});

test("a replacement review invalidates the previous payload and cached drafts cost no extra call", async () => {
  const context = await buildFixture();
  const payloads: string[] = [];
  const drafts = createSkillDrafts({
    ...context,
    engine: {
      engine: "claude-code",
      runner: async (run) => {
        payloads.push(run.prompt);

        return generationResult(syntheticSkill);
      },
    },
  });
  const replaced = await drafts.preview(syntheticBrief);
  const current = await drafts.preview({
    ...syntheticBrief,
    body: "Compare three measurements.",
  });

  await expect(drafts.generate({ id: replaced.id })).rejects.toThrow(
    "Review a fresh",
  );
  await drafts.generate({ id: current.id });

  const cached = await drafts.preview({
    ...syntheticBrief,
    body: "Compare three measurements.",
  });

  expect(cached.cached).toEqual(syntheticSkill);
  expect(await drafts.generate({ id: cached.id })).toEqual(syntheticSkill);
  expect(payloads).toEqual([current.payload]);
});
