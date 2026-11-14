import { fingerprint } from "../shared/structured";
import { profile, profileText, repositoryInstructions } from "./fixtures/profile";
import { tasks } from "./fixtures/tasks";

export const fixedDefinition = {
  version: 1,
  name: "engineering-preferences-v1",
  profile,
  profileText,
  repositoryInstructions,
  tasks,
  functionalChecks: ["concise-advice/content"],
};

export const benchmarkFingerprint = fingerprint(fixedDefinition);
export const fixedArms = ["bare", "profile", "shadowclone"] as const;
export const internalArms = ["bare", "original", "first-time"] as const;
export const armNames = { bare: "bare", original: "profile", "first-time": "shadowclone" } as const;
