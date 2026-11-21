import type { ProjectPaths } from "@shadowclone/core";
import { listSkillProposals, readSkillProposal, saveSkillProposal } from "@shadowclone/skills";
import type { DiscoveredSkill, SkillConflictProposal } from "@shadowclone/skills";
import { shareSkillScope, type SkillPair } from "./catalog";
import type { assessSkillConflict } from "./assess";

export async function currentConflictProposals(options: {
  readonly paths: ProjectPaths;
  readonly skills: readonly DiscoveredSkill[];
}): Promise<SkillConflictProposal[]> {
  const proposals: SkillConflictProposal[] = [];

  for (const entry of await listSkillProposals(options.paths)) {
    if (entry.kind !== "conflict") continue;

    const proposal = await readSkillProposal({ paths: options.paths, id: entry.id });
    if (proposal.kind !== "conflict") continue;

    const [first, second] = proposal.sources.map((source) => options.skills.find((skill) =>
      skill.id === source.skillId && skill.fingerprint === source.sourceFingerprint,
    ));

    if (first && second && shareSkillScope([first, second])) {
      if (proposal.status !== "superseded") proposals.push(proposal);
    } else if (proposal.status === "pending") {
      await saveSkillProposal({ paths: options.paths, proposal: { ...proposal, status: "superseded" } });
    }
  }

  return proposals;
}

export async function saveConflictProposal(options: {
  readonly paths: ProjectPaths;
  readonly pair: SkillPair;
  readonly inputFingerprint: string;
  readonly assessment: Awaited<ReturnType<typeof assessSkillConflict>>;
}): Promise<SkillConflictProposal> {
  const [left, right] = options.pair;
  const source = (entry: { readonly skill: DiscoveredSkill; readonly passage: string }) => ({
    rootId: entry.skill.root.id,
    skillId: entry.skill.id,
    name: entry.skill.name,
    sourceRelativePath: entry.skill.relativePath,
    sourceFingerprint: entry.skill.fingerprint,
    passage: entry.passage,
  });
  const proposal: SkillConflictProposal = {
    id: crypto.randomUUID(),
    kind: "conflict",
    sources: [
      source({ skill: left, passage: options.assessment.leftPassage }),
      source({ skill: right, passage: options.assessment.rightPassage }),
    ],
    workflow: options.assessment.workflow,
    decision: options.assessment.decision,
    findings: ["conflict"],
    status: "pending",
    createdAt: Date.now(),
    inputFingerprint: options.inputFingerprint,
  };

  await saveSkillProposal({ paths: options.paths, proposal });
  return proposal;
}
