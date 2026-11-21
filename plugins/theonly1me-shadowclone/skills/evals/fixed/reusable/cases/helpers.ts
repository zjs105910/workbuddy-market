import { fileSchema } from "../../../native/schema";
import { caseSchema, type Family, type PreferenceCase } from "../schema";
import type { StudyCheck } from "../../../native/study/checkSchema";

export const fixtureFile = (options: { path: string; content: string }) =>
  fileSchema.parse(options);
export function implementationCase(options: {
  id: string;
  family: Family;
  request: string;
  initial: string;
  reference: string;
  assertions: string;
  specification: string;
  checks: StudyCheck[];
  extraChecks?: PreferenceCase["extraChecks"];
  repository?: PreferenceCase["repository"];
  turns?: string[];
  split?: PreferenceCase["split"];
}): PreferenceCase {
  const source = fixtureFile({ path: "src/subject.ts", content: options.initial });
  return caseSchema.parse({
    family: options.family,
    split: options.split ?? "development",
    repository: options.repository ?? "atlas",
    specification: options.specification,
    extraChecks: options.extraChecks ?? [],
    task: {
      id: options.id,
      mode: "code",
      turns: [options.request, ...(options.turns ?? [])],
      fixtures: [],
      git: {
        checkout: "work",
        pushed: false,
        branches: [
          { name: "work", commits: [{ message: "chore: initialize fixture", files: [source] }] },
        ],
      },
      acceptance: {
        files: [
          fixtureFile({
            path: "acceptance.test.ts",
            content: `import { expect, test } from "bun:test";\nimport * as subject from "./src/subject";\ntest("acceptance", async () => {\n${options.assertions}\n});\n`,
          }),
        ],
        commands: [{ arguments: ["bun", "test", "acceptance.test.ts"] }],
        reference: [fixtureFile({ path: "src/subject.ts", content: options.reference })],
      },
      checks: options.checks,
    },
  });
}
export function adviceCase(options: {
  id: string;
  request: string;
  checks: StudyCheck[];
  specification: string;
  extraChecks?: PreferenceCase["extraChecks"];
  correctnessChecks?: StudyCheck[];
  split?: PreferenceCase["split"];
}): PreferenceCase {
  return caseSchema.parse({
    family: "length",
    split: options.split ?? "development",
    repository: "atlas",
    specification: options.specification,
    extraChecks: options.extraChecks ?? [],
    correctnessChecks: options.correctnessChecks ?? [],
    task: {
      id: options.id,
      mode: "advice",
      turns: [options.request],
      git: null,
      fixtures: [],
      acceptance: null,
      checks: options.checks,
    },
  });
}
export const check = (options: {
  family: Family;
  kind: "no-added-comments" | "no-unsafe-types" | "options-object" | "no-git-writes";
}): StudyCheck => ({ id: options.family, keyItem: options.family, kind: options.kind });
export const increment = {
  initial: "export function increment(value: number): number { return value; }\n",
  reference: "export function increment(value: number): number { return value + 1; }\n",
  assertions: "expect(subject.increment(3)).toBe(4);\nexpect(subject.increment(-1)).toBe(0);",
};
