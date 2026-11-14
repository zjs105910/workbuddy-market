import { z } from "zod";

export const activitySchema = z.object({
  reviews: z.array(z.object({ id: z.number(), body: z.string().nullable(), submitted_at: z.string().nullable(), user: z.object({ login: z.string() }) })),
  reviewComments: z.array(
    z.object({
      pull_request_review_id: z.number().nullable(),
      path: z.string(),
      line: z.number().nullable(),
      original_line: z.number().nullable().optional(),
      body: z.string(),
      user: z.object({ login: z.string() }),
    }),
  ),
  issueComments: z.array(z.object({ body: z.string().nullable(), user: z.object({ login: z.string() }), created_at: z.string() })),
});

export type Activity = z.infer<typeof activitySchema>;
