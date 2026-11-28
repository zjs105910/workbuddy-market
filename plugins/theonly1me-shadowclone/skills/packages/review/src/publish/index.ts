import { z } from "zod";
import { hostEnvironment, runProcess } from "@shadowclone/core";
import type { ReviewResult } from "../types";
import { reviewPayload } from "./payload";

export { reviewMarker, reviewPayload } from "./payload";

const postedReviewSchema = z.object({ html_url: z.url() });

export async function publishReview(options: {
  readonly result: ReviewResult;
  readonly cwd: string;
}): Promise<string> {
  const { pull } = options.result;

  if (pull.number === null) {
    throw new Error("A branch review has no pull request to post to.");
  }

  const posted = await runProcess({
    arguments: [
      "gh",
      "api",
      "--method",
      "POST",
      `repos/${pull.repository}/pulls/${pull.number}/reviews`,
      "--input",
      "-",
    ],
    cwd: options.cwd,
    environment: hostEnvironment({ remote: true }),
    input: JSON.stringify(reviewPayload(options.result)),
    timeoutMilliseconds: 60_000,
  });

  if (posted.exitCode !== 0) {
    throw new Error(`GitHub refused the review: ${posted.stderr.trim().slice(0, 300)}`);
  }

  return postedReviewSchema.parse(JSON.parse(posted.stdout)).html_url;
}
