import type { ManagedPolicy, ProjectPaths } from "@shadowclone/core";
import { initializeSkillEnvironment, registerWorkingRepository } from "@shadowclone/environment";
import { importRepositoryGuidance, maintainSkills } from "@shadowclone/learning";
import {
  configureSkillMaintenance,
} from "@shadowclone/skills";
import type { InitializeOptions } from "./init";
import type { OnboardingPresence } from "./onboardingPresence";

export async function prepareInitialEnvironment(
  options: InitializeOptions & {
    readonly paths: ProjectPaths;
    readonly workingDirectory: string;
    readonly policy: ManagedPolicy;
    readonly learn: boolean;
    readonly skills: boolean;
    readonly presence: OnboardingPresence;
    readonly writeLine: (line: string) => void;
  },
): Promise<{ readonly rulesLearned: number; readonly skillsSynced: number }> {
  const {
    paths,
    workingDirectory,
    policy,
    learn,
    skills,
    presence,
    writeLine,
  } = options;

  if (
    skills &&
    policy.enabled &&
    policy.allowedSources.includes("skill-library")
  ) {
    await configureSkillMaintenance({
      scope: "global",
      paths,
      cwd: workingDirectory,
      managedConfigPath: options.managedConfigPath,
    });
  }

  if (policy.enabled) {
    await initializeSkillEnvironment({ paths, automatic: skills });
  }

  if (skills && policy.enabled && policy.allowedSources.includes("skill-library")) {
    await registerWorkingRepository({
      paths,
      workingDirectory,
      gitMetadataEnabled:
        learn && policy.allowedSources.includes("git-metadata"),
      blockedOrigins: policy.blockedOrigins,
      managedConfigPath: options.managedConfigPath,
      readRemote: options.readRemote,
    });
  }

  let rulesLearned = 0;

  if (
    learn &&
    presence.hasRepositoryGuidance &&
    policy.enabled &&
    policy.allowedSources.includes("declared-rules")
  ) {
    const imported = await importRepositoryGuidance({
      paths,
      workingDirectory,
      gitMetadataEnabled: policy.allowedSources.includes("git-metadata"),
      blockedOrigins: policy.blockedOrigins,
      readRemote: options.readRemote,
    });

    rulesLearned += imported.imported;
  }

  let skillsSynced = 0;

  if (
    skills &&
    policy.enabled &&
    policy.allowedSources.includes("skill-library")
  ) {
    await configureSkillMaintenance({
      scope: "global",
      paths,
      cwd: workingDirectory,
      managedConfigPath: options.managedConfigPath,
    });

    const updated = await maintainSkills({
      paths,
      syncPersonal: true,
      managedConfigPath: options.managedConfigPath,
      readRemote: options.readRemote,
    });

    skillsSynced = updated.synced;

    if (updated.conflicts > 0) {
      writeLine(`${updated.conflicts} skill conflicts need review.`);
    }
  }

  return { rulesLearned, skillsSynced };
}
