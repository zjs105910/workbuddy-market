import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import { updateLearningEnvironment } from "../../environmentUpdate/update";
import { applySkillProposal } from "../apply";
import { readMaintenanceState } from "@shadowclone/skills";
import { listSkillProposals, readSkillProposal, showSkillProposal } from "@shadowclone/skills";
import { conflictExecution, conflictFixture, forbiddenTable, requiredTable, syntheticSecret } from "../../testing";

test("active updates review the whole library without new learning and queue a supported conflict", async () => {
  const setup = await conflictFixture();
  const prompts: string[] = [];

  try {
    const execution = conflictExecution({ onPrompt: (prompt) => prompts.push(prompt) });
    const summary = await updateLearningEnvironment({ ...setup, execution });

    expect(summary).toMatchObject({ conflicts: 1, pending: 1, libraryReviewed: 2, libraryDeferred: 0 });
    const [entry] = await listSkillProposals(setup.paths);
    if (!entry) throw new Error("Expected the conflict proposal");

    const proposal = await readSkillProposal({ paths: setup.paths, id: entry.id });
    if (proposal.kind !== "conflict") throw new Error("Expected a conflict");

    expect(proposal.sources.map(({ passage }) => passage).sort()).toEqual([forbiddenTable, requiredTable].sort());
    expect(proposal.decision).toContain("whether dependency tables belong");
    expect(await showSkillProposal({ paths: setup.paths, id: proposal.id })).toContain("Writing release notes");
    await expect(applySkillProposal({ ...setup, id: proposal.id })).rejects.toThrow("precedence decision");
    expect(await Bun.file(setup.filePath).text()).toBe(setup.personal);
    expect(await Bun.file(setup.thirdPartyPath).text()).toBe(setup.thirdParty);
    expect(prompts.join("\n")).not.toContain(syntheticSecret);
    expect(prompts.join("\n")).not.toContain(setup.home);
    for (const source of proposal.sources) {
      expect(prompts.join("\n")).not.toContain(source.skillId);
    }

    expect(await updateLearningEnvironment({ ...setup, execution }))
      .toMatchObject({ libraryReviewed: 0, libraryDeferred: 0, pending: 1 });
    expect(execution.callsUsed()).toBe(2);
    expect(await listSkillProposals(setup.paths)).toHaveLength(1);
    expect(Object.values((await readMaintenanceState(setup.paths)).findings).flat())
      .toContain("library-conflict");
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});

test("invented conflicting passages leave the comparison unfinished", async () => {
  const setup = await conflictFixture();

  try {
    expect(await updateLearningEnvironment({ ...setup, execution: conflictExecution({ fabricatedPassage: true }) }))
      .toMatchObject({ pending: 0, libraryDeferred: 1 });
    expect(await listSkillProposals(setup.paths)).toEqual([]);
    expect(await Bun.file(setup.filePath).text()).toBe(setup.personal);
    expect(await updateLearningEnvironment({ ...setup, execution: conflictExecution() }))
      .toMatchObject({ libraryReviewed: 1, libraryDeferred: 0, pending: 1 });
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
