import path from "node:path";
import { fingerprint } from "../../shared/structured";
import { fixedGraderFingerprint } from "../identity";

export async function graderFingerprint() {
  if (!(await Bun.file(path.join(import.meta.dir, "grading.ts")).exists()))
    throw new Error("This contributor evaluation requires a Shadowclone source checkout.");
  const sources: [string, string][] = [];
  for (const name of [
    "grading.ts",
    "validation.ts",
    "examples.ts",
    "scoring.ts",
    "intervals.ts",
    "report.ts",
    "execution.ts",
    "attempts.ts",
    "dispatchHold.ts",
    "schema.ts",
    "assessment.ts",
    "accounting.ts",
  ]) {
    sources.push([name, await Bun.file(path.join(import.meta.dir, name)).text()]);
  }
  return fingerprint({ native: await fixedGraderFingerprint(), sources });
}
