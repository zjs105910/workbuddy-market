import { temporaryRepository } from "./discovery.fixtures";
import { expect, test } from "bun:test";
import { mkdir, symlink } from "node:fs/promises";
import path from "node:path";
import { discoverRepositoryGuidance } from "./discovery";

test("ignores linked skills without reading their targets", async () => {
  const repository = await temporaryRepository();
  const target = await temporaryRepository();
  const skill = path.join(repository, ".claude", "skills", "linked");

  await mkdir(path.dirname(skill), { recursive: true });
  await Bun.write(path.join(target, "SKILL.md"), "external guidance");
  await Bun.write(path.join(repository, "CLAUDE.md"), "root guidance");

  const regularSkill = path.join(
    repository,
    ".claude",
    "skills",
    "regular",
    "SKILL.md",
  );

  await mkdir(path.dirname(regularSkill), { recursive: true });
  await Bun.write(regularSkill, "regular guidance");
  await symlink(target, skill);

  const sources = await discoverRepositoryGuidance(repository);

  expect(sources.map((source) => source.relativePath)).toEqual([
    ".claude/skills/regular/SKILL.md",
    "CLAUDE.md",
  ]);
});

for (const filename of ["AGENTS.md", "CLAUDE.md", ".cursorrules"]) {
  test(`ignores a linked ${filename} root file`, async () => {
    const repository = await temporaryRepository();
    const outsideRepository = await temporaryRepository();
    const regularFilename =
      filename === "AGENTS.md" ? "CLAUDE.md" : "AGENTS.md";

    await Bun.write(
      path.join(outsideRepository, filename),
      "external guidance",
    );
    await Bun.write(path.join(repository, regularFilename), "regular guidance");
    await symlink(
      path.join(outsideRepository, filename),
      path.join(repository, filename),
    );

    const sources = await discoverRepositoryGuidance(repository);

    expect(sources.map((source) => source.relativePath)).toEqual([
      regularFilename,
    ]);
  });
}

for (const rootName of [".agents", ".claude"]) {
  test(`ignores a linked ${rootName} parent root`, async () => {
    const repository = await temporaryRepository();
    const outsideRepository = await temporaryRepository();

    const externalSkill = path.join(
      outsideRepository,
      "skills",
      "external",
      "SKILL.md",
    );

    await mkdir(path.dirname(externalSkill), { recursive: true });
    await Bun.write(externalSkill, "external guidance");
    await Bun.write(path.join(repository, "AGENTS.md"), "regular guidance");
    await symlink(outsideRepository, path.join(repository, rootName));

    const sources = await discoverRepositoryGuidance(repository);

    expect(sources.map((source) => source.relativePath)).toEqual(["AGENTS.md"]);
  });

  test(`ignores a linked ${rootName}/skills root`, async () => {
    const repository = await temporaryRepository();
    const outsideRepository = await temporaryRepository();
    const externalSkill = path.join(outsideRepository, "external", "SKILL.md");

    await mkdir(path.dirname(externalSkill), { recursive: true });
    await Bun.write(externalSkill, "external guidance");
    await Bun.write(path.join(repository, "AGENTS.md"), "regular guidance");
    await mkdir(path.join(repository, rootName));
    await symlink(outsideRepository, path.join(repository, rootName, "skills"));

    const sources = await discoverRepositoryGuidance(repository);

    expect(sources.map((source) => source.relativePath)).toEqual(["AGENTS.md"]);
  });
}

test("ignores a linked SKILL.md while retaining regular guidance", async () => {
  const repository = await temporaryRepository();
  const outsideRepository = await temporaryRepository();

  const linkedSkill = path.join(
    repository,
    ".agents",
    "skills",
    "linked",
    "SKILL.md",
  );

  const regularSkill = path.join(
    repository,
    ".agents",
    "skills",
    "regular",
    "SKILL.md",
  );

  await mkdir(path.dirname(linkedSkill), { recursive: true });
  await mkdir(path.dirname(regularSkill), { recursive: true });
  await Bun.write(
    path.join(outsideRepository, "SKILL.md"),
    "external guidance",
  );
  await Bun.write(regularSkill, "regular guidance");
  await symlink(path.join(outsideRepository, "SKILL.md"), linkedSkill);

  const sources = await discoverRepositoryGuidance(repository);

  expect(sources.map((source) => source.relativePath)).toEqual([
    ".agents/skills/regular/SKILL.md",
  ]);
});
