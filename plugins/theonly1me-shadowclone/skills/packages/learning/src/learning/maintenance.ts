import type { LearningExecution } from "@shadowclone/agents";
import { updateLearningEnvironment } from "./environmentUpdate/update";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { updateLegacySkillLibrary, type SkillUpdateSummary } from "./skillMaintenance/legacyUpdate";

export async function maintainSkills(options: {
  readonly paths: ProjectPaths;
  readonly execution?: LearningExecution;
  readonly syncPersonal?: boolean;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<SkillUpdateSummary> {
  const environment = await updateLearningEnvironment(options);
  return environment ?? await updateLegacySkillLibrary(options);
}
