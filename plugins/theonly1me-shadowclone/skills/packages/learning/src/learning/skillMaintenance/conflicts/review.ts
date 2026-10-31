import type { LearningExecution } from "@shadowclone/agents";
import type { ProjectPaths } from "@shadowclone/core";
import { writeMaintenanceState } from "@shadowclone/skills";
import type { DiscoveredSkill, MaintenanceState } from "@shadowclone/skills";
import { assessCatalogOverlap, assessSkillConflict } from "./assess";
import { comparisonFingerprint, libraryCatalogBatches, type SkillPair } from "./catalog";
import { currentConflictProposals, saveConflictProposal } from "./proposals";

export async function reviewDiscoveredSkills(options: {
  readonly paths: ProjectPaths;
  readonly execution: LearningExecution;
  readonly state: MaintenanceState;
  readonly skills: readonly DiscoveredSkill[];
}) {
  const batches = libraryCatalogBatches(options.skills);
  const identifiers = new Set(batches.map((batch) => batch.fingerprint));
  const catalogs = Object.fromEntries(Object.entries(options.state.libraryReview?.catalogs ?? {})
    .filter(([key]) => identifiers.has(key)));
  const comparisons = new Set(options.state.libraryReview?.comparisons ?? []);
  const proposals = await currentConflictProposals(options);
  const pairs = new Map<string, SkillPair>();
  let reviewed = 0;
  let available = true;

  const checkpoint = async () => {
    const findings = Object.fromEntries(Object.entries(options.state.findings)
      .map(([key, values]) => [key, values.filter((value) => value !== "library-conflict")]));

    for (const proposal of proposals.filter(({ status }) => status === "pending")) {
      for (const source of proposal.sources) {
        findings[source.skillId] = [...new Set([...(findings[source.skillId] ?? []), "library-conflict"])];
      }
    }

    await writeMaintenanceState({
      paths: options.paths,
      state: { ...options.state, findings, libraryReview: { catalogs, comparisons: [...comparisons] } },
    });
  };

  for (const batch of batches) {
    if (!catalogs[batch.fingerprint] && available && options.execution.callsRemaining() > 0) {
      let overlaps: readonly SkillPair[];

      try {
        overlaps = await assessCatalogOverlap({ ...options, batch, cwd: options.paths.shadowcloneDirectory });
      } catch {
        available = false;
        continue;
      }

      catalogs[batch.fingerprint] = overlaps.map(([left, right]) => [left.id, right.id]);
      reviewed += 1;
      await checkpoint();
    }

    for (const [leftId, rightId] of catalogs[batch.fingerprint] ?? []) {
      const left = options.skills.find(({ id }) => id === leftId);
      const right = options.skills.find(({ id }) => id === rightId);
      if (!left || !right) continue;

      const pair: SkillPair = [left, right];
      const inputFingerprint = comparisonFingerprint(pair);
      pairs.set(inputFingerprint, pair);

      if (comparisons.has(inputFingerprint)) continue;

      if (proposals.some((proposal) => proposal.inputFingerprint === inputFingerprint)) {
        comparisons.add(inputFingerprint);
        continue;
      }

      if (!available || options.execution.callsRemaining() === 0) continue;

      let assessment: Awaited<ReturnType<typeof assessSkillConflict>>;

      try {
        assessment = await assessSkillConflict({ ...options, pair, cwd: options.paths.shadowcloneDirectory });
      } catch {
        available = false;
        continue;
      }

      if (assessment.conflict) {
        proposals.push(await saveConflictProposal({ ...options, pair, inputFingerprint, assessment }));
      }

      comparisons.add(inputFingerprint);
      reviewed += 1;
      await checkpoint();
    }
  }

  for (const key of comparisons) {
    if (!pairs.has(key)) comparisons.delete(key);
  }

  await checkpoint();

  return {
    reviewed,
    deferred: batches.filter((batch) => !catalogs[batch.fingerprint]).length +
      [...pairs.keys()].filter((key) => !comparisons.has(key)).length,
    pending: proposals.filter(({ status }) => status === "pending").length,
  };
}
