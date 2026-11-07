import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { ghJson } from "../github";
import { upstreamPullSchema } from "../mine/pulls";
import { evalCaseSchema, type SelectedCase, selectedCaseSchema } from "../sample";
import { caseCommits, pushCase } from "./branches";
import { sanitizeBody } from "./sanitize";

export const copiedCaseSchema = evalCaseSchema.extend({ number: z.number().int().positive() });

export type CopiedCase = z.infer<typeof copiedCaseSchema>;

const createdPullSchema = z.object({ number: z.number().int().positive() });

async function copyCase(options: {
  readonly entry: SelectedCase;
  readonly clone: string;
  readonly evalRepository: string;
  readonly upstream: z.infer<typeof upstreamPullSchema>;
}): Promise<CopiedCase> {
  const { entry, clone, evalRepository } = options;
  const commits = await caseCommits({ clone, id: entry.id, upstream: entry.upstream, baseSha: options.upstream.base.sha });

  await pushCase({ clone, remote: `git@github.com:${evalRepository}.git`, id: entry.id, ...commits });

  const created = createdPullSchema.parse(
    await ghJson([
      "api",
      "--method",
      "POST",
      `repos/${evalRepository}/pulls`,
      "-f",
      `title=${sanitizeBody(options.upstream.title)}`,
      "-f",
      `body=${sanitizeBody(options.upstream.body ?? "")}`,
      "-f",
      `head=case-${entry.id}/head`,
      "-f",
      `base=case-${entry.id}/base`,
      "-F",
      "draft=true",
    ]),
  );

  return { ...entry, number: created.number, baseSha: commits.base, headSha: commits.head };
}

export async function copyCases(options: {
  readonly mined: string;
  readonly clone: string;
  readonly evalRepository: string;
  readonly only?: readonly string[];
}): Promise<readonly CopiedCase[]> {
  const selected = z.array(selectedCaseSchema).parse(JSON.parse(readFileSync(path.join(options.mined, "selected.json"), "utf8")));
  const pulls = new Map(z.array(upstreamPullSchema).parse(JSON.parse(readFileSync(path.join(options.mined, "pulls.json"), "utf8"))).map((pull) => [pull.number, pull]));
  const copiedFile = path.join(options.mined, "copied.json");
  const copied: CopiedCase[] = (() => {
    try {
      return z.array(copiedCaseSchema).parse(JSON.parse(readFileSync(copiedFile, "utf8")));
    } catch {
      return [];
    }
  })();

  for (const entry of selected.filter((candidate) => options.only === undefined || options.only.includes(candidate.id))) {
    const upstream = pulls.get(entry.upstream);

    if (upstream === undefined || copied.some((done) => done.id === entry.id)) {
      continue;
    }

    try {
      copied.push(await copyCase({ entry, clone: options.clone, evalRepository: options.evalRepository, upstream }));
      writeFileSync(copiedFile, JSON.stringify(copied, null, 2));
      console.error(`copied ${entry.id} from upstream ${entry.upstream}`);
    } catch (error) {
      console.error(`skipped ${entry.id}: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  return copied;
}
