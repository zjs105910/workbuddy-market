import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import { updateLearningEnvironment } from "../../environmentUpdate/update";
import { listSkillProposals, readSkillProposal, rejectSkillProposal } from "@shadowclone/skills";
import { conflictExecution, conflictFixture } from "../../testing";

test("a bounded review resumes the full-document comparison from the cached catalog", async () => {
  const setup = await conflictFixture();

  try {
    const first = conflictExecution({ maximumCalls: 1 });
    expect(await updateLearningEnvironment({ ...setup, execution: first }))
      .toMatchObject({ libraryReviewed: 1, libraryDeferred: 1, pending: 0 });
    expect(first.callsUsed()).toBe(1);
    expect(await listSkillProposals(setup.paths)).toEqual([]);

    const second = conflictExecution({ maximumCalls: 1, onPrompt: (prompt) => {
      expect(prompt).toContain("Review overlapping skill documents");
    } });
    expect(await updateLearningEnvironment({ ...setup, execution: second }))
      .toMatchObject({ libraryReviewed: 1, libraryDeferred: 0, pending: 1 });
    expect(second.callsUsed()).toBe(1);
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});

test("source edits invalidate the reviewed pair and preserve the earlier proposal", async () => {
  const setup = await conflictFixture();

  try {
    await updateLearningEnvironment({ ...setup, execution: conflictExecution() });
    const [earlier] = await listSkillProposals(setup.paths);
    if (!earlier) throw new Error("Expected the earlier proposal");

    await Bun.write(setup.filePath, `${setup.personal}\nKeep release notes concise.\n`);
    const execution = conflictExecution();
    expect(await updateLearningEnvironment({ ...setup, execution }))
      .toMatchObject({ libraryReviewed: 2, pending: 1 });
    expect((await readSkillProposal({ paths: setup.paths, id: earlier.id })).status).toBe("superseded");
    expect(await listSkillProposals(setup.paths)).toHaveLength(2);
    expect(await Bun.file(setup.filePath).text()).toContain("Keep release notes concise.");
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});

test("rejecting a conflict does not rewrite its sources or recreate the same proposal", async () => {
  const setup = await conflictFixture();

  try {
    await updateLearningEnvironment({ ...setup, execution: conflictExecution() });
    const [proposal] = await listSkillProposals(setup.paths);
    if (!proposal) throw new Error("Expected a proposal");

    await rejectSkillProposal({ paths: setup.paths, id: proposal.id });
    expect(await updateLearningEnvironment({ ...setup, execution: conflictExecution() }))
      .toMatchObject({ pending: 0, libraryReviewed: 0 });
    expect(await listSkillProposals(setup.paths)).toHaveLength(1);
    expect(await Bun.file(setup.filePath).text()).toBe(setup.personal);
    expect(await Bun.file(setup.thirdPartyPath).text()).toBe(setup.thirdParty);
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
