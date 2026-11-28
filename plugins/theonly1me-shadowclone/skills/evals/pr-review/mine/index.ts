import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { blamedPulls } from "./blame";
import { mergedPulls, upstreamPullSchema } from "./pulls";
import { type CleanCase, type DefectCase, isFix, isReviewable, pickIntroducing } from "./select";

function option(name: string): string {
  const index = process.argv.indexOf(name);
  const value = index < 0 ? undefined : process.argv[index + 1];

  if (value === undefined) {
    throw new Error(`Use bun evals/pr-review/mine/index.ts --repo owner/name --clone <dir> --since <date> --introduced-before <date> --fix-within-days <days> --until <date> --output <dir>; missing ${name}`);
  }

  return value;
}

const repository = option("--repo");
const clone = option("--clone");
const output = option("--output");
const since = option("--since");
const until = option("--until");
const introducedBefore = option("--introduced-before");
const fixWithinDays = Number(option("--fix-within-days"));
const pullsFile = path.join(output, "pulls.json");

mkdirSync(output, { recursive: true });

const cached = (() => {
  try {
    return z.array(upstreamPullSchema).parse(JSON.parse(readFileSync(pullsFile, "utf8")));
  } catch {
    return null;
  }
})();
const pulls = cached ?? (await mergedPulls({ repository, since, until }));

writeFileSync(pullsFile, JSON.stringify(pulls));

const byNumber = new Map(pulls.map((pull) => [pull.number, pull]));
const fixes = pulls.filter(isFix).filter((pull) => pull.merge_commit_sha !== null);
const defects: DefectCase[] = [];

for (const fix of fixes) {
  const blamed = await blamedPulls({ clone, fixCommit: fix.merge_commit_sha ?? "" });
  const picked = pickIntroducing({ fix, blamed, pulls: byNumber, introducedBefore, fixWithinDays });

  if (picked !== null && !defects.some((entry) => entry.introducing === picked.introducing)) {
    defects.push(picked);
  }
}

const defective = new Set(defects.map((entry) => entry.introducing));
const clean: CleanCase[] = pulls
  .filter((pull) => isReviewable(pull) && (pull.merged_at ?? "") < introducedBefore && !defective.has(pull.number) && !isFix(pull))
  .map((pull) => ({ kind: "clean", introducing: pull.number }));

writeFileSync(path.join(output, "cases.json"), JSON.stringify({ repository, since, until, introducedBefore, defects, clean }, null, 2));
console.log(`${pulls.length} merged pulls, ${fixes.length} fixes, ${defects.length} defect cases, ${clean.length} clean candidates`);
