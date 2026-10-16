import { portableFixture } from "./portable.fixtures";
import { expect, test } from "bun:test";
import { cp } from "node:fs/promises";
import path from "node:path";
import {
  readPortableSkills,
  skillTreeFingerprint,
  syncPortableSkills,
} from "./portable";
import { writePortableSkills } from "./portableFiles";

test("copies a complete portable skill and promotes one edited replica", async () => {
  const setup = await portableFixture();
  const initialFingerprints = await Promise.all(
    setup.destinations.map(skillTreeFingerprint),
  );

  expect(new Set(initialFingerprints).size).toBe(1);

  for (const destination of setup.destinations) {
    expect(
      await Bun.file(path.join(destination, "references/checklist.md")).text(),
    ).toBe("Verify the requested behavior.\n");
  }

  const claudeSkill = path.join(setup.destinations[1] ?? "", "SKILL.md");

  await Bun.write(
    claudeSkill,
    `${await Bun.file(claudeSkill).text()}\nClaude edit\n`,
  );

  expect(await syncPortableSkills({ paths: setup.paths })).toEqual({
    synced: 2,
    conflicts: 0,
  });

  for (const destination of setup.destinations) {
    expect(await Bun.file(path.join(destination, "SKILL.md")).text()).toContain(
      "Claude edit",
    );
  }
});

for (const legacyDirectory of [".codex/skills", ".cursor/skills"]) {
  test(`retires a matching legacy ${legacyDirectory} replica after synchronization`, async () => {
    const setup = await portableFixture();
    const legacySkill = path.join(
      setup.home,
      legacyDirectory,
      "portable-workflow",
    );

    await cp(setup.destinations[0] ?? "", legacySkill, { recursive: true });

    const [portable] = await readPortableSkills(setup.paths);

    if (portable === undefined) {
      throw new Error("Portable skill must be registered");
    }

    await writePortableSkills({
      paths: setup.paths,
      skills: [
        {
          ...portable,
          replicaDirectories: [...portable.replicaDirectories, legacySkill],
        },
      ],
    });

    expect(await syncPortableSkills({ paths: setup.paths })).toEqual({
      synced: 1,
      conflicts: 0,
    });
    expect(await Bun.file(legacySkill).exists()).toBeFalse();
    expect(
      (await readPortableSkills(setup.paths))[0]?.replicaDirectories,
    ).not.toContain(legacySkill);
  });
}

test("retires an unchanged legacy Codex replica after another replica changes", async () => {
  const setup = await portableFixture();
  const codexSkill = path.join(setup.home, ".codex/skills/portable-workflow");

  await cp(setup.destinations[0] ?? "", codexSkill, { recursive: true });

  const [portable] = await readPortableSkills(setup.paths);

  if (portable === undefined) {
    throw new Error("Portable skill must be registered");
  }

  await writePortableSkills({
    paths: setup.paths,
    skills: [
      {
        ...portable,
        replicaDirectories: [...portable.replicaDirectories, codexSkill],
      },
    ],
  });

  const claudeSkill = path.join(setup.destinations[1] ?? "", "SKILL.md");

  await Bun.write(
    claudeSkill,
    `${await Bun.file(claudeSkill).text()}\nClaude edit\n`,
  );

  expect(await syncPortableSkills({ paths: setup.paths })).toEqual({
    synced: 3,
    conflicts: 0,
  });
  expect(await Bun.file(codexSkill).exists()).toBeFalse();
  expect(
    await Bun.file(path.join(setup.destinations[0] ?? "", "SKILL.md")).exists(),
  ).toBeTrue();
});

test("preserves a divergent legacy Codex replica as a conflict", async () => {
  const setup = await portableFixture();
  const codexSkill = path.join(setup.home, ".codex/skills/portable-workflow");

  await cp(setup.destinations[0] ?? "", codexSkill, { recursive: true });

  const [portable] = await readPortableSkills(setup.paths);

  if (portable === undefined) {
    throw new Error("Portable skill must be registered");
  }

  await writePortableSkills({
    paths: setup.paths,
    skills: [
      {
        ...portable,
        replicaDirectories: [...portable.replicaDirectories, codexSkill],
      },
    ],
  });
  await Bun.write(
    path.join(codexSkill, "SKILL.md"),
    `${await Bun.file(path.join(codexSkill, "SKILL.md")).text()}\nCodex edit\n`,
  );

  expect(await syncPortableSkills({ paths: setup.paths })).toEqual({
    synced: 0,
    conflicts: 1,
  });
  expect(await Bun.file(path.join(codexSkill, "SKILL.md")).text()).toContain(
    "Codex edit",
  );
  expect(
    await Bun.file(path.join(setup.destinations[0] ?? "", "SKILL.md")).text(),
  ).not.toContain("Codex edit");
});

test("preserves divergent portable skill edits as a conflict", async () => {
  const setup = await portableFixture();
  const canonicalSkill = path.join(setup.destinations[0] ?? "", "SKILL.md");
  const claudeSkill = path.join(setup.destinations[1] ?? "", "SKILL.md");
  const geminiSkill = path.join(setup.destinations[2] ?? "", "SKILL.md");
  const original = await Bun.file(canonicalSkill).text();

  await Bun.write(claudeSkill, `${original}\nClaude edit\n`);
  await Bun.write(geminiSkill, `${original}\nGemini edit\n`);

  expect(await syncPortableSkills({ paths: setup.paths })).toEqual({
    synced: 0,
    conflicts: 1,
  });
  expect(await Bun.file(canonicalSkill).text()).toBe(original);
  expect(await Bun.file(claudeSkill).text()).toContain("Claude edit");
  expect(await Bun.file(geminiSkill).text()).toContain("Gemini edit");
});
