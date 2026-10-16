import path from "node:path";
import { fingerprint, acquireLocalLock } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { readSkillProposal, saveSkillProposal } from "./proposals";
import { readMaintenanceState, writeMaintenanceState } from "./state";

export async function rejectSkillProposal(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
}): Promise<void> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "skills-worker.db"),
  );

  if (!lock) {
    throw new Error("Another skill update is running");
  }

  try {
    const proposal = await readSkillProposal(options);

    if (proposal.status !== "pending") {
      throw new Error("Skill proposal is no longer pending");
    }

    if (proposal.kind === "conflict") {
      await saveSkillProposal({ paths: options.paths, proposal: { ...proposal, status: "rejected" } });
      return;
    }

    const state = await readMaintenanceState(options.paths);

    await writeMaintenanceState({
      paths: options.paths,
      state: {
        ...state,
        rejected: {
          ...state.rejected,
          [proposal.skillId]: [
            ...new Set([
              ...(state.rejected[proposal.skillId] ?? []),
              fingerprint(proposal.after),
            ]),
          ],
        },
      },
    });
    await saveSkillProposal({
      paths: options.paths,
      proposal: { ...proposal, status: "rejected" },
    });
  } finally {
    lock.release();
  }
}
