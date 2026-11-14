import { z } from "zod";
import { runHostCommand } from "@shadowclone/core";
import { pullFactsSchema, type PullFacts } from "../types";

const pullViewSchema = z.object({
  number: z.number().int().positive(),
  title: z.string(),
  body: z.string(),
  baseRefName: z.string(),
  baseRefOid: z.string(),
  headRefOid: z.string(),
});

export async function readPullFacts(options: {
  readonly repository: string;
  readonly number: number;
  readonly cwd: string;
}): Promise<PullFacts> {
  const result = await runHostCommand({
    arguments: [
      "gh",
      "pr",
      "view",
      String(options.number),
      "--repo",
      options.repository,
      "--json",
      "number,title,body,baseRefName,baseRefOid,headRefOid",
    ],
    cwd: options.cwd,
  });

  if (result.exitCode !== 0) {
    throw new Error(
      `gh could not read pull request ${options.number}: ${result.stderr.trim().slice(0, 300)}`,
    );
  }

  const view = pullViewSchema.parse(JSON.parse(result.stdout));

  return pullFactsSchema.parse({
    repository: options.repository,
    number: view.number,
    title: view.title,
    body: view.body,
    baseRefName: view.baseRefName,
    baseSha: view.baseRefOid,
    headSha: view.headRefOid,
  });
}
