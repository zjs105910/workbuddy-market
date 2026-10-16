import { learningSnapshot, storeLearningRules } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import { readLegacyProfileSnapshot, type ProfileSnapshot } from "@shadowclone/profile";
import { writeLegacyProfile } from "@shadowclone/profile";
import type { ProfileRule, ProfileRuleReference, ProfileWriteResult } from "@shadowclone/profile";
import type { LearningProvenance } from "./provenance";

export async function readLearningSnapshot(paths: ProjectPaths): Promise<ProfileSnapshot> {
  return await learningSnapshot(paths) ?? await readLegacyProfileSnapshot(paths);
}

export async function persistLearningRules(options: {
  readonly paths: ProjectPaths;
  readonly rules: readonly ProfileRule[];
  readonly retired?: readonly ProfileRuleReference[];
  readonly provenance?: Readonly<Record<string, LearningProvenance>>;
}): Promise<ProfileWriteResult> {
  return await storeLearningRules(options) ?? await writeLegacyProfile(options);
}
