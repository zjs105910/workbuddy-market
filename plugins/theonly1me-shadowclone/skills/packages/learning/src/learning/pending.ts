import path from "node:path";
import { z } from "zod";
import { readLocalText, replaceLocalText, acquireLocalLock, sourceIds } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { ProfileRule } from "@shadowclone/profile";
import { learningRuleSchema } from "@shadowclone/environment";
import type { IndexedEvent, CorrectionSignal } from "@shadowclone/sessions";
import { learningRuleProvenance } from "./provenance";

const pendingSchema = z.strictObject({
  rules: z.array(learningRuleSchema),
  rejectedKeys: z.array(z.string()),
  provenance: z.record(z.string(), z.strictObject({
    sources: z.array(z.enum(sourceIds)),
    complete: z.boolean(),
  })).default({}),
});

type PendingState = z.infer<typeof pendingSchema>;

export function pendingLearningFile(paths: ProjectPaths): string {
  return path.join(paths.shadowcloneDirectory, "learning-pending.json");
}

export async function readPendingLearning(paths: ProjectPaths): Promise<PendingState> {
  const contents = await readLocalText(pendingLearningFile(paths));

  return contents === null
    ? { rules: [], rejectedKeys: [], provenance: {} }
    : pendingSchema.parse(JSON.parse(contents));
}

export async function updatePendingLearning(options: {
  readonly paths: ProjectPaths;
  readonly update: (state: PendingState) => PendingState | Promise<PendingState>;
}): Promise<PendingState> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "learning-pending.db"),
  );

  if (!lock) {
    throw new Error("Another learning review is running");
  }

  try {
    const filePath = pendingLearningFile(options.paths);
    const previous = await readLocalText(filePath);
    const current = previous === null
      ? { rules: [], rejectedKeys: [], provenance: {} }
      : pendingSchema.parse(JSON.parse(previous));
    const next = pendingSchema.parse(await options.update(current));

    await replaceLocalText({
      filePath,
      previous,
      next: `${JSON.stringify(next, null, 2)}\n`,
    });

    return next;
  } finally {
    lock.release();
  }
}

export async function queuePendingLearning(options: {
  readonly paths: ProjectPaths;
  readonly rules: readonly ProfileRule[];
  readonly events: readonly IndexedEvent[];
  readonly signals: readonly CorrectionSignal[];
}): Promise<number> {
  let queued = 0;

  await updatePendingLearning({
    paths: options.paths,
    update: (state) => {
      const rules = new Map(state.rules.map((rule) => [rule.key, rule]));
      const provenance = { ...state.provenance };

      for (const rule of options.rules) {
        if (!state.rejectedKeys.includes(rule.key)) {
          rules.set(rule.key, learningRuleSchema.parse(rule));
          const evidence = learningRuleProvenance({
            rule,
            events: options.events,
            signals: options.signals,
          });
          provenance[rule.key] = {
            sources: [...evidence.sources],
            complete: evidence.complete,
          };
          queued += 1;
        }
      }

      return { ...state, rules: [...rules.values()], provenance };
    },
  });

  return queued;
}
