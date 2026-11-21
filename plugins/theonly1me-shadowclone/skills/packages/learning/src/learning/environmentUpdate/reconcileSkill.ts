import type { FileUpdate } from "@shadowclone/changes";
import type { LearningExecution } from "@shadowclone/agents";
import type { ProjectPaths } from "@shadowclone/core";
import type { DiscoveredSkill } from "@shadowclone/skills";
import { draftSkill, applySkillDraft } from "./draft";
import { pendingDraftReasons } from "./draftReview";
import {
  coveredLearningState,
  type EnvironmentState,
  generatedSkillBody,
  type LearningRecord,
  type LearningScope,
  pendingLearningState,
  type SkillDraft,
  skillPublication,
  validateRouting,
} from "@shadowclone/environment";
import { resolveLearningTarget, existingLearningSkill } from "./learningTarget";
import type { LearningRoute } from "./planner";

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function reconcileSkillLearning(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly records: readonly LearningRecord[];
  readonly keys: ReadonlySet<string>;
  readonly route: LearningRoute;
  readonly scope: LearningScope;
  readonly skills: readonly DiscoveredSkill[];
  readonly execution: LearningExecution;
}): Promise<{ readonly state: EnvironmentState; readonly updates: readonly FileUpdate[]; readonly applied: number }> {
  const { records, route } = options;
  const targetDetails = await resolveLearningTarget(options);
  const { selected, companion, name, target, rawOriginal, original } = targetDetails;
  const pending = (reason: string) => ({
    state: pendingLearningState({
      ...options,
      reasons: records.map(({ rule }) => ({ key: rule.key, reason })),
      destinations: [target],
    }),
    updates: [],
    applied: 0,
  });
  const draftFor = (repair?: { readonly draft: SkillDraft; readonly error: string }) =>
    draftSkill({
      original,
      name,
      description: route.description,
      records,
      execution: options.execution,
      cwd: options.paths.shadowcloneDirectory,
      ...(repair ? { repair } : {}),
    });
  const reviewNeeded = (candidate: SkillDraft) =>
    candidate.outcomes.some(({ disposition }) => disposition === "pending")
      ? {
          state: pendingLearningState({
            ...options,
            reasons: pendingDraftReasons(candidate),
            destinations: [target],
          }),
          updates: [],
          applied: 0,
        }
      : selected &&
          !companion &&
          selected.raw !== selected.redacted &&
          candidate.edits.some((edit) => edit.before && !selected.raw.includes(edit.before))
        ? pending(
            "The proposed edit overlaps redacted content. Review the target skill locally before retrying.",
          )
        : null;
  const apply = (candidate: SkillDraft) =>
    applySkillDraft({
      draft:
        companion && rawOriginal === null
          ? {
              ...candidate,
              description: `Use only with the already selected ${selected.name} skill. ${candidate.description || route.description}`,
              body: `# Local guidance for ${selected.name}\n\nUse these instructions only when the installed ${selected.name} skill is already selected. Preserve its workflow and permissions. If it is unavailable, report that limitation.\n\n${generatedSkillBody({ text: candidate.body, name })}`,
            }
          : candidate,
      original: rawOriginal,
      name,
      description: route.description,
      records,
    });
  const draft = await draftFor();
  const firstReview = reviewNeeded(draft);

  if (firstReview) {
    return firstReview;
  }

  if (
    selected && selected.valid !== false && !companion &&
    draft.edits.length === 0 && !draft.body &&
    (!draft.description || draft.description === selected.description)
  ) {
    return {
      state: coveredLearningState({
        ...options,
        target,
        fingerprint: selected.fingerprint,
      }),
      updates: [],
      applied: 0,
    };
  }

  let text: string;

  try {
    text = apply(draft);
  } catch (error) {
    const firstError = messageOf(error);

    if (options.execution.callsRemaining() < 1) {
      return pending(`The draft failed validation: ${firstError}. No learning call was left for a repair turn. Retry this learning.`);
    }

    let repaired: SkillDraft;

    try {
      repaired = await draftFor({ draft, error: firstError });
    } catch {
      return pending(`The draft failed validation: ${firstError}. The repair turn did not return a valid draft. Retry this learning.`);
    }

    const repairReview = reviewNeeded(repaired);

    if (repairReview) {
      return repairReview;
    }

    try {
      text = apply(repaired);
    } catch (secondError) {
      return pending(`The draft failed validation: ${firstError}. One repair turn also failed: ${messageOf(secondError)}. Review the target document and retry this learning.`);
    }
  }

  let publication: Awaited<ReturnType<typeof skillPublication>>;

  try {
    publication = await skillPublication({
      ...options,
      skill: existingLearningSkill({ ...targetDetails, scope: options.scope, route }),
      name,
      text,
    });
  } catch {
    return pending("Publication needs review of destination ownership or supporting files. Resolve the target conflict and retry this learning.");
  }

  try {
    validateRouting({ paths: options.paths, state: publication.state });
  } catch {
    return pending("Native skill routing exceeds its 4 KiB budget. Shorten validated skill descriptions or narrow the selected routes before retrying.");
  }

  return { ...publication, applied: 1 };
}
