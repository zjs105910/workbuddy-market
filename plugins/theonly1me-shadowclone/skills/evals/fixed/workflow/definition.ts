import { fixedDefinition } from "../definition";
import { fingerprint } from "../../shared/structured";
import { corrections } from "./fixtures";

export const workflowArms = ["bare", "skills", "routing", "deep"] as const;
export const workflowInternalArms = ["bare", "original", "first-time", "deep"] as const;
export const workflowArmNames = { bare: "bare", original: "skills", "first-time": "routing", deep: "deep" } as const;
export const existingPreferenceIds = ["comments", "types", "parameters"] as const;
const existingIds = new Set<string>(existingPreferenceIds);

export const existingSkill = `---\nname: personal-engineering\ndescription: Apply the user's code style and API conventions when writing or reviewing code.\n---\n\n# Personal engineering\n\n${fixedDefinition.profile.filter(rule => existingIds.has(rule.id)).map(rule => `- ${rule.statement}`).join("\n")}\n`;

export const workflowDefinition = {
  version: 2,
  name: "engineering-preferences-four-setups-v1",
  profile: fixedDefinition.profile.map(rule => ({ ...rule, group: existingIds.has(rule.id) ? "personal" as const : "learned" as const })),
  tasks: fixedDefinition.tasks,
  repositoryInstructions: fixedDefinition.repositoryInstructions,
  functionalChecks: fixedDefinition.functionalChecks,
  existingSkill,
  corrections,
};

export const workflowBenchmarkFingerprint = fingerprint(workflowDefinition);
