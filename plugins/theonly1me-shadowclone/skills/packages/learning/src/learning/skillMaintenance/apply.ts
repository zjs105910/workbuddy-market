import path from "node:path";
import { commitLocalChanges } from "@shadowclone/changes";
import {
  readEffectiveConfig,
  fingerprint,
  readLocalText,
  acquireLocalLock,
} from "@shadowclone/core";
import { compileContext } from "@shadowclone/environment";
import type { GitRemoteReader } from "@shadowclone/sessions";
import type { ProjectPaths } from "@shadowclone/core";
import { parseSkillDocument, validateSkillReferences } from "@shadowclone/skills";
import { readSkillProposal, saveSkillProposal } from "@shadowclone/skills";
import { companionPrefix } from "@shadowclone/skills";
import {
  isPluginCache,
  readMaintenanceState,
  skillTarget,
  writeMaintenanceState,
} from "@shadowclone/skills";

type ApplyOptions = {
  readonly paths: ProjectPaths;
  readonly id: string;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
};

export async function applySkillProposalUnlocked(
  options: ApplyOptions,
): Promise<string | null> {
  const { config } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? options.paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!config.sources["skill-library"]) {
    throw new Error("Skill library access is disabled");
  }

  const proposal = await readSkillProposal(options);

  if (proposal.kind === "conflict") {
    throw new Error("Conflict proposals require a precedence decision. Review both sources, resolve the owning instructions, and run skills update again.");
  }

  if (proposal.status !== "pending") {
    throw new Error("Skill proposal is no longer pending");
  }

  const state = await readMaintenanceState(options.paths);
  const root = state.roots.find((entry) => entry.id === proposal.rootId);

  if (!root?.enabled) {
    throw new Error("Skill source is no longer configured");
  }

  if (
    (await compileContext({
      ...options,
      cwd: root.cwd,
      scope: root.scope === "global" ? "global" : "combined",
    })) === null
  ) {
    throw new Error("Skill scope is blocked by managed policy");
  }

  const companion = proposal.kind === "companion";

  if (
    companion
      ? root.owner !== "third-party" ||
        proposal.targetRelativePath !==
          `${companionPrefix}${proposal.skillId.slice(0, 20)}/SKILL.md`
      : root.owner !== "user" ||
        proposal.targetRelativePath !== proposal.sourceRelativePath
  ) {
    throw new Error("Skill proposal has an invalid destination");
  }

  const sourcePath = skillTarget({
    directory: root.directory,
    relativePath: proposal.sourceRelativePath,
  });

  if (!companion && isPluginCache(sourcePath)) {
    throw new Error("Installed plugin caches cannot be modified");
  }

  const source = await readLocalText(sourcePath);

  if (source === null || fingerprint(source) !== proposal.sourceFingerprint) {
    throw new Error(
      "Skill source changed since assessment; files were preserved",
    );
  }

  const directory = companion ? root.destination : root.directory;
  const filePath = skillTarget({
    directory,
    relativePath: proposal.targetRelativePath,
  });

  if (isPluginCache(filePath)) {
    throw new Error("Skill destinations cannot be inside plugin caches");
  }

  const parsed = parseSkillDocument(proposal.after);

  if (parsed.metadata.name !== path.basename(path.dirname(filePath))) {
    throw new Error("Skill name differs from its destination");
  }

  await validateSkillReferences({ filePath, text: parsed.body, mentionedFiles: "required" });

  const previousTracking = state.tracked.find(
    (entry) => entry.id === proposal.skillId,
  );

  const tracking = {
    id: proposal.skillId,
    rootId: root.id,
    relativePath: proposal.targetRelativePath,
    fingerprint: fingerprint(proposal.after),
    kind: proposal.kind,
    automatic: previousTracking?.automatic === true,
  };

  const nextState = {
    ...state,
    tracked: [
      ...state.tracked.filter((entry) => entry.id !== proposal.skillId),
      tracking,
    ],
  };

  await writeMaintenanceState({ paths: options.paths, state: nextState });

  let revision: string | null;

  try {
    revision = await commitLocalChanges({
      paths: options.paths,
      root: directory,
      kind: "skill",
      updates: [{ filePath, previous: proposal.before, next: proposal.after }],
    });
  } catch (error) {
    await writeMaintenanceState({ paths: options.paths, state });

    throw error;
  }

  await saveSkillProposal({
    paths: options.paths,
    proposal: { ...proposal, status: "applied" },
  });

  return revision;
}

export async function applySkillProposal(
  options: ApplyOptions,
): Promise<string | null> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "skills-worker.db"),
  );

  if (!lock) {
    throw new Error("Another skill update is running");
  }

  try {
    return await applySkillProposalUnlocked(options);
  } finally {
    lock.release();
  }
}
