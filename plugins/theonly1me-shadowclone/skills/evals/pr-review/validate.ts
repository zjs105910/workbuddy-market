import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import { runProcess } from "@shadowclone/core";
import { inBatches } from "./github";
import { askJudges } from "./judges";
import { upstreamPullSchema } from "./mine/pulls";

const verdictSchema = z.object({
  fixRepairsIntroducedDefect: z.boolean(),
  defect: z.string().max(400),
  reason: z.string().max(600),
});

const defectSchema = z.object({ introducing: z.number(), fix: z.number(), fixCommit: z.string(), blamedLines: z.number() });
const validatedSchema = defectSchema.extend({
  verdicts: z.array(z.object({ judge: z.enum(["opus", "sol"]), output: verdictSchema.nullable(), error: z.string().nullable() })),
  valid: z.boolean(),
});
const casesSchema = z.object({ defects: z.array(defectSchema), clean: z.array(z.object({ introducing: z.number() })) });

async function diff(options: { readonly clone: string; readonly range: readonly string[] }): Promise<string> {
  const result = await runProcess({ arguments: ["git", "diff", "--no-color", ...options.range], cwd: options.clone, environment: process.env, timeoutMilliseconds: 60_000 });

  return result.stdout.slice(0, 60_000);
}

function prompt(options: { readonly introducingTitle: string; readonly introducingDiff: string; readonly fixTitle: string; readonly fixDiff: string }): string {
  return `Two merged pull requests from one repository follow. Decide whether the second one repairs a defect that the first one introduced.
Answer true only when the first pull request added or changed code that causes the failure that the second one repairs. Answer false when the second pull request repairs an older problem, adds a feature, changes behavior on purpose, or only touches nearby lines.
Describe the defect in one or two plain sentences, as a reviewer of the first pull request would have reported it.

<first_pull_request title="${options.introducingTitle.replaceAll('"', "'")}">
${options.introducingDiff}
</first_pull_request>
<second_pull_request title="${options.fixTitle.replaceAll('"', "'")}">
${options.fixDiff}
</second_pull_request>`;
}

export async function validateDefects(options: { readonly mined: string; readonly clone: string }): Promise<void> {
  const cases = casesSchema.parse(JSON.parse(readFileSync(path.join(options.mined, "cases.json"), "utf8")));
  const pulls = new Map(z.array(upstreamPullSchema).parse(JSON.parse(readFileSync(path.join(options.mined, "pulls.json"), "utf8"))).map((pull) => [pull.number, pull]));
  const neutral = mkdtempSync(path.join(os.tmpdir(), "pr-review-validate-"));
  const previousFile = path.join(options.mined, "validated.json");
  const previous = new Map(
    (existsSync(previousFile) ? z.array(validatedSchema).parse(JSON.parse(readFileSync(previousFile, "utf8"))) : []).map((entry) => [`${entry.introducing}-${entry.fix}`, entry]),
  );
  const results = await inBatches({
    items: cases.defects,
    size: 4,
    work: async (defect) => {
      const known = previous.get(`${defect.introducing}-${defect.fix}`);

      if (known !== undefined) {
        return known;
      }

      const introducing = pulls.get(defect.introducing);
      const fix = pulls.get(defect.fix);

      if (introducing?.merge_commit_sha == null || fix === undefined) {
        return { ...defect, verdicts: [], valid: false };
      }

      const answers = await askJudges({
        prompt: prompt({
          introducingTitle: introducing.title,
          introducingDiff: await diff({ clone: options.clone, range: [`${introducing.merge_commit_sha}^`, introducing.merge_commit_sha] }),
          fixTitle: fix.title,
          fixDiff: await diff({ clone: options.clone, range: [`${defect.fixCommit}^`, defect.fixCommit] }),
        }),
        schema: verdictSchema,
        cwd: neutral,
      });

      return { ...defect, verdicts: answers, valid: answers.every((answer) => answer.output?.fixRepairsIntroducedDefect === true) };
    },
  });

  writeFileSync(path.join(options.mined, "validated.json"), JSON.stringify(results, null, 2));
  console.log(`${results.filter((entry) => entry.valid).length} of ${results.length} defect cases validated by both judges`);
}
