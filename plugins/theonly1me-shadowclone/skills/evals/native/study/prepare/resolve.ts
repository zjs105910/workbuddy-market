import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import { ownedWrite } from "@shadowclone/core";
import { listSkillProposals, rejectSkillProposal, readSkillProposal } from "@shadowclone/skills";
import { applySkillProposal } from "@shadowclone/learning";

export type Resolution = {
  readonly applied: readonly string[];
  readonly rejected: readonly string[];
  readonly conflicts: readonly string[];
};

export async function applyPendingChanges(options: {
  readonly paths: ProjectPaths;
  readonly directory: string;
}): Promise<Resolution> {
  const applied: string[] = [];
  const rejected: string[] = [];
  const conflicts: { id: string; workflow: string; decision: string; passages: readonly string[] }[] = [];

  for (const entry of await listSkillProposals(options.paths)) {
    if (entry.status !== "pending") {
      continue;
    }

    const proposal = await readSkillProposal({ paths: options.paths, id: entry.id });

    if (proposal.kind === "conflict") {
      conflicts.push({
        id: proposal.id, workflow: proposal.workflow, decision: proposal.decision,
        passages: proposal.sources.map((source) => `${source.name}: ${source.passage}`),
      });
      continue;
    }

    try {
      await applySkillProposal({ paths: options.paths, id: proposal.id, managedConfigPath: null });
      applied.push(proposal.id);
    } catch {
      await rejectSkillProposal({ paths: options.paths, id: proposal.id });
      rejected.push(proposal.id);
    }
  }

  await ownedWrite({
    path: path.join(options.directory, "pending-conflicts.json"),
    content: JSON.stringify(conflicts, null, 2),
  });
  return { applied, rejected, conflicts: conflicts.map((conflict) => conflict.id) };
}
