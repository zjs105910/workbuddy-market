import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import type { SkillAssessment } from "./assess";
import { applySkillProposalUnlocked } from "./apply";
import { assessmentFingerprint, prepareSkillProposal } from "./prepare";
import { saveSkillProposal } from "@shadowclone/skills";
import { readMaintenanceState, writeMaintenanceState } from "@shadowclone/skills";
import type { DiscoveredSkill, MaintenanceState } from "@shadowclone/skills";

export function nextSkillBatch(
  skills: readonly DiscoveredSkill[],
): readonly DiscoveredSkill[] {
  const batch: DiscoveredSkill[] = [];
  let bytes = 0;

  for (const skill of skills) {
    if (
      batch.length === 4 ||
      bytes + Buffer.byteLength(skill.redacted) > 64_000
    ) {
      break;
    }

    batch.push(skill);
    bytes += Buffer.byteLength(skill.redacted);
  }

  return batch;
}

export async function applyAssessedSkills(options: {
  readonly paths: ProjectPaths;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
  readonly assessments: readonly {
    readonly skill: DiscoveredSkill;
    readonly assessment: SkillAssessment;
  }[];
  readonly state: MaintenanceState;
  readonly profile: string;
  readonly duplicates: number;
  readonly summary: {
    assessed: number;
    applied: number;
    pending: number;
    verification: number;
  };
}): Promise<MaintenanceState> {
  let state = options.state;

  for (const { skill, assessment } of options.assessments) {
    options.summary.assessed += 1;

    if (assessment.decision === "needs-verification") {
      options.summary.verification += 1;
    }

    const prepared = await prepareSkillProposal({
      paths: options.paths,
      skill,
      assessment,
      state,
      profile: options.profile,
    });

    if (prepared) {
      await saveSkillProposal({
        paths: options.paths,
        proposal: prepared.proposal,
      });

      if (prepared.automatic && options.duplicates === 0) {
        await applySkillProposalUnlocked({
          paths: options.paths,
          id: prepared.proposal.id,
          managedConfigPath: options.managedConfigPath,
          readRemote: options.readRemote,
        });
        options.summary.applied += 1;
        state = await readMaintenanceState(options.paths);
      } else {
        options.summary.pending += 1;
      }
    }

    state = {
      ...state,
      assessed: {
        ...state.assessed,
        [skill.id]: assessmentFingerprint({ skill, profile: options.profile }),
      },
      findings: {
        ...state.findings,
        [skill.id]: [
          ...assessment.findings,
          ...(assessment.decision === "needs-verification"
            ? ["needs-verification"]
            : []),
        ],
      },
    };
    await writeMaintenanceState({ paths: options.paths, state });
  }

  return state;
}
