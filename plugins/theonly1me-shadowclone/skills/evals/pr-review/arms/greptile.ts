import { z } from "zod";
import { postComment, reviewActivity, waitFor } from "./poll";
import type { ArmRunner } from "./types";

const reviewsSchema = z.array(z.object({ id: z.number(), submitted_at: z.string().nullable(), user: z.object({ login: z.string() }) }));

export const runGreptile: ArmRunner = async ({ entry, evalRepository }) => {
  const startedAt = new Date().toISOString();

  await postComment({ repository: evalRepository, number: entry.number, body: "@greptileai" });

  const review = await waitFor({
    timeoutMilliseconds: 45 * 60_000,
    intervalMilliseconds: 30_000,
    check: async () => {
      const activity = await reviewActivity({ repository: evalRepository, number: entry.number });
      const found = reviewsSchema.parse(activity.reviews).find((candidate) => /greptile/i.test(candidate.user.login) && (candidate.submitted_at ?? "") >= startedAt);

      return found === undefined ? null : { found, activity };
    },
  });

  return {
    arm: "greptile",
    caseId: entry.id,
    number: entry.number,
    startedAt,
    finishedAt: review?.found.submitted_at ?? null,
    status: review === null ? "timed-out" : "done",
    detail: review === null ? "no review within 45 minutes" : `review ${review.found.id}`,
    raw: review?.activity ?? null,
  };
};
