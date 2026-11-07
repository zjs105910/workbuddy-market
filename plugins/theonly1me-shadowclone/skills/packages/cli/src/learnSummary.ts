import type { SkillUpdateSummary } from "@shadowclone/learning";

export function writeSkillMaintenance(options: {
  readonly skills: SkillUpdateSummary;
  readonly writeLine: (line: string) => void;
}): void {
  const { skills } = options;

  options.writeLine(
    `Skill maintenance: ${skills.synced} synced, ${skills.applied} updated, ${skills.pending} pending, ${skills.deferred} deferred, ${skills.conflicts} conflicts.`,
  );

  if ((skills.held ?? 0) > 0) {
    options.writeLine(
      `${skills.held} learned rule(s) held for review, because their text reads like instructions to an agent. Run shadowclone learning pending to see each reason.`,
    );
  }
}
