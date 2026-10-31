import { expect, test } from "bun:test";
import path from "node:path";
import { applySkillProposal } from "./apply";
import { skillExecution, skillFixture } from "@shadowclone/environment/testing";
import { adoptSkill, inspectSkillLibrary } from "./lifecycle";
import { listSkillProposals, restoreOriginalSkill, rejectSkillProposal } from "@shadowclone/skills";
import { updateSkillLibrary } from "./update";

test("user-owned changes stay pending until a specific proposal is approved", async () => {
  const setup = await skillFixture();

  const summary = await updateSkillLibrary({
    ...setup,
    execution: skillExecution({
      description: "Apply type-safe feature changes when implementing code.",
    }),
  });

  expect(summary).toMatchObject({ assessed: 1, applied: 0, pending: 1 });
  expect(await Bun.file(setup.filePath).text()).toBe(setup.original);

  const [proposal] = await listSkillProposals(setup.paths);

  if (!proposal) {
    throw new Error("Expected a skill proposal");
  }

  await applySkillProposal({ ...setup, id: proposal.id });

  const updated = await Bun.file(setup.filePath).text();

  expect(updated).toContain("Use complete names.");
  expect(updated).toContain("disable-model-invocation: true");
  expect(updated).toContain("Preserve the requested behavior.");
  expect(restoreOriginalSkill(updated)).toBe(setup.original);
});

test("adopted skills update automatically but preserve later manual edits", async () => {
  const setup = await skillFixture();
  const [skill] = (await inspectSkillLibrary(setup)).skills;

  if (!skill) {
    throw new Error("Expected a skill");
  }

  await adoptSkill({ ...setup, id: skill.id });

  expect(
    await updateSkillLibrary({ ...setup, execution: skillExecution() }),
  ).toMatchObject({ applied: 1, pending: 0 });

  const edited = (await Bun.file(setup.filePath).text()).replace(
    "Preserve the requested behavior.",
    "My manually revised workflow.",
  );

  await Bun.write(setup.filePath, edited);
  await Bun.write(
    path.join(setup.paths.profileDirectory, "global/engineering.md"),
    "## Tests\n\nRun focused tests after editing.\n",
  );

  expect(
    await updateSkillLibrary({
      ...setup,
      execution: skillExecution({
        passage: "Run focused tests after editing.",
      }),
    }),
  ).toMatchObject({ applied: 0, pending: 1 });
  expect(await Bun.file(setup.filePath).text()).toBe(edited);
});

test("rejected identical changes remain rejected after unrelated profile updates", async () => {
  const setup = await skillFixture();

  await updateSkillLibrary({ ...setup, execution: skillExecution() });

  const [proposal] = await listSkillProposals(setup.paths);

  if (!proposal) {
    throw new Error("Expected a skill proposal");
  }

  await rejectSkillProposal({ ...setup, id: proposal.id });
  await Bun.write(
    path.join(setup.paths.profileDirectory, "global/workflow.md"),
    "## Verification\n\nVerify before handing off work.\n",
  );

  expect(
    await updateSkillLibrary({ ...setup, execution: skillExecution() }),
  ).toMatchObject({ assessed: 1, pending: 0, applied: 0 });
  expect(await listSkillProposals(setup.paths)).toHaveLength(1);
});

test("apply refuses a source that changed after assessment", async () => {
  const setup = await skillFixture();

  await updateSkillLibrary({ ...setup, execution: skillExecution() });

  const [proposal] = await listSkillProposals(setup.paths);

  if (!proposal) {
    throw new Error("Expected a skill proposal");
  }

  await Bun.write(setup.filePath, `${setup.original}\nManual addition\n`);
  await expect(
    applySkillProposal({ ...setup, id: proposal.id }),
  ).rejects.toThrow("changed since assessment");

  expect(await Bun.file(setup.filePath).text()).toContain("Manual addition");
});
