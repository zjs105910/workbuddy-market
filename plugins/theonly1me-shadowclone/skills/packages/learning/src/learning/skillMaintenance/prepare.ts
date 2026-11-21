import { fingerprint, readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { readEnvironment } from "@shadowclone/environment";
import {
  parseSkillDocument,
  companionPrefix,
  renderCompanionSkill,
  renderMaintainedSkill,
  restoreOriginalSkill,
  skillTarget,
} from "@shadowclone/skills";
import type { SkillAssessment } from "./assess";
import type { DiscoveredSkill, MaintenanceState, SkillChangeProposal } from "@shadowclone/skills";

export function assessmentFingerprint(options: {
  readonly skill: DiscoveredSkill;
  readonly profile: string;
}): string {
  return fingerprint(
    JSON.stringify({
      version: 1,
      skill: options.skill.redacted,
      profile: options.profile,
    }),
  );
}

export async function prepareSkillProposal(options: {
  readonly paths: ProjectPaths;
  readonly skill: DiscoveredSkill;
  readonly assessment: SkillAssessment;
  readonly state: MaintenanceState;
  readonly profile: string;
}): Promise<{
  readonly proposal: SkillChangeProposal;
  readonly automatic: boolean;
} | null> {
  if (
    options.assessment.decision !== "update" ||
    options.assessment.passages.length === 0
  ) {
    return null;
  }

  const { skill, assessment } = options;
  const companion = skill.root.owner === "third-party";
  const kind = companion ? "companion" : "amend";
  const targetRelativePath = companion
    ? `${companionPrefix}${skill.id.slice(0, 20)}/SKILL.md`
    : skill.relativePath;
  const target = skillTarget({
    directory: companion ? skill.root.destination : skill.root.directory,
    relativePath: targetRelativePath,
  });
  const before = companion ? await readLocalText(target) : skill.raw;

  const after = companion
    ? renderCompanionSkill({
        skillId: skill.id,
        name: skill.name,
        description: assessment.description || skill.description,
        passages: assessment.passages,
        metadata: parseSkillDocument(skill.redacted).metadata,
      })
    : renderMaintainedSkill({
        original: skill.raw,
        description: assessment.description,
        passages: assessment.passages,
      });

  parseSkillDocument(after);

  if (!companion) {
    restoreOriginalSkill(after);
  }

  if (options.state.rejected[skill.id]?.includes(fingerprint(after))) {
    return null;
  }

  if (before === after) {
    return null;
  }

  const tracking = options.state.tracked.find((entry) => entry.id === skill.id);
  const environment = await readEnvironment(options.paths);
  const buildOwned = environment?.artifacts.some(
    (artifact) => artifact.buildId && artifact.filePath === target,
  );
  const conflicts =
    assessment.findings.includes("conflict") ||
    assessment.findings.includes("technical-verification");

  const automatic =
    tracking?.automatic === true &&
    !buildOwned &&
    before !== null &&
    fingerprint(before) === tracking.fingerprint &&
    !assessment.description &&
    !conflicts;

  return {
    automatic,
    proposal: {
      id: crypto.randomUUID(),
      rootId: skill.root.id,
      skillId: skill.id,
      sourceRelativePath: skill.relativePath,
      sourceFingerprint: skill.fingerprint,
      targetRelativePath,
      kind,
      before,
      after,
      findings: assessment.findings,
      status: "pending",
      createdAt: Date.now(),
      inputFingerprint: assessmentFingerprint({
        skill,
        profile: options.profile,
      }),
    },
  };
}
