import { z } from "zod";
import { ghJson, inBatches } from "../github";

export const upstreamPullSchema = z.object({
  number: z.number().int().positive(),
  title: z.string(),
  body: z.string().nullable(),
  user: z.object({ login: z.string(), type: z.string() }),
  merged_at: z.string().nullable(),
  merge_commit_sha: z.string().nullable(),
  base: z.object({ sha: z.string(), ref: z.string() }),
  head: z.object({ sha: z.string() }),
  additions: z.number().int(),
  deletions: z.number().int(),
  changed_files: z.number().int(),
});

export type UpstreamPull = z.infer<typeof upstreamPullSchema>;

const searchSchema = z.object({ total_count: z.number(), items: z.array(z.object({ number: z.number() })) });

export async function mergedPulls(options: {
  readonly repository: string;
  readonly since: string;
  readonly until: string;
}): Promise<readonly UpstreamPull[]> {
  const numbers: number[] = [];

  for (let page = 1; page <= 10; page += 1) {
    const result = searchSchema.parse(
      await ghJson([
        "api",
        "-X",
        "GET",
        "search/issues",
        "-f",
        `q=repo:${options.repository} is:pr is:merged merged:${options.since}..${options.until}`,
        "-f",
        "per_page=100",
        "-f",
        `page=${page}`,
      ]),
    );

    numbers.push(...result.items.map((item) => item.number));

    if (numbers.length >= result.total_count || result.items.length === 0) {
      break;
    }
  }

  return inBatches({
    items: numbers,
    size: 8,
    work: async (number) => upstreamPullSchema.parse(await ghJson(["api", `repos/${options.repository}/pulls/${number}`])),
  });
}
