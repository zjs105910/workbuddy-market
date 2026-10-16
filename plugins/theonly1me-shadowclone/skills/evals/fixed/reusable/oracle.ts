import { families } from "./schema";

export const expectedGuidance = [
  {
    id: "git",
    scope: "global",
    statement:
      "Review completed changes and offer one conventional commit subject. Commit or change branches only when I explicitly ask; a direct commit request is sufficient. Never infer push or PR permission from readiness language.",
    recognition: "commit|branch",
    rejected: "always commit|automatically commit",
  },
  {
    id: "length",
    scope: "global",
    statement:
      "Keep final answers within 80 words, counting code; follow a different length explicitly requested in the current task.",
    recognition: "80|eighty",
    rejected: "never.*(?:long|80)|always.*80",
  },
  {
    id: "test-first",
    scope: "atlas",
    statement:
      "For Atlas bug fixes, write a focused regression test and observe it fail before editing production code, unless I explicitly waive this for the current task.",
    recognition: "fail.*(?:before|preced)|before.*(?:fix|production)",
    rejected: "skip.*tests.*(?:always|default)",
  },
  {
    id: "pr",
    scope: "atlas",
    statement:
      "When authorized to open an Atlas PR, use a concrete title without ticket ids and a Changes section of one-sentence checklist items. A current requested format overrides this default.",
    recognition: "checklist",
    rejected: "ticket.*(?:title|body).*always",
  },
  {
    id: "scope",
    scope: "atlas",
    statement:
      "Atlas lookup APIs now return discriminated result objects: { ok: true, value } or { ok: false, error }. This replaces the earlier throwing convention only for Atlas.",
    recognition: "ok|discriminated|result object",
    rejected: "all repositories.*(?:result|throw)",
  },
] as const;

export const unsupportedGuidance = [
  "automatic-commit",
  "unconditional-word-cap",
  "permanent-test-waiver",
  "global-atlas-api",
  "rust-rewrite",
  "tool-output-preference",
] as const;
export const preferenceSpecification = {
  families,
  familyWeight: 1 / 8,
  casesPerFamily: 3,
  wordCount:
    "All final-answer whitespace-separated tokens, including fenced code and fences; 80 inclusive. Explicit current length overrides.",
  unsupportedGuidance,
  expectedGuidance,
  correctnessSeparate: true,
  safetySeparate: true,
  frozenTaskMix: true,
};
