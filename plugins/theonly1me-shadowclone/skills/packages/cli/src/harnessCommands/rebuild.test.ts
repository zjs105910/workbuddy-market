import { expect, test } from "bun:test";
import path from "node:path";
import { checkoutRoot } from "@shadowclone/core/testing";
import { harnessInitCommand } from "../harness";
import { acceptAll, type FixtureRepository, harnessTestSetup } from "@shadowclone/harness/testing";

const repositoryRoot = await checkoutRoot();
const personalSkills = ["scope-confirmed-changes", "tests-that-catch-bugs"] as const;
const tasteRules = [
  "## File size\n\nKeep every file under 200 lines, tests included.\n",
  "## Comments\n\nWrite zero comments in TypeScript files.\n",
  "## Prose\n\nNo em-dashes anywhere in code or prose.\n",
  "## Suppressions\n\nNever silence a lint or type rule with a suppression.\n",
].join("\n");

async function repositoryText(relativePath: string): Promise<string> {
  return Bun.file(path.join(repositoryRoot, relativePath)).text();
}

async function strippedShadowclone(): Promise<FixtureRepository> {
  const files: Record<string, string> = { "bun.lock": "{}\n" };

  for (const relativePath of [
    "package.json",
    "tsconfig.base.json",
    "biome.json",
    ".github/workflows/ci.yml",
  ]) {
    files[relativePath] = await repositoryText(relativePath);
  }

  return {
    name: "shadowclone-stripped",
    files,
    specification: "",
    acceptance: {},
    acceptanceCommand: "",
  };
}

test("harness init rebuilds this repository's harness from its manifests and the owner's taste", async () => {
  const setup = await harnessTestSetup({
    fixture: await strippedShadowclone(),
    globalRules: tasteRules,
    sources: { "skill-library": true },
  });

  for (const skill of personalSkills) {
    await Bun.write(
      path.join(setup.home, ".agents/skills", skill, "SKILL.md"),
      await repositoryText(`skills/${skill}/SKILL.md`),
    );
  }

  await harnessInitCommand({
    apply: true,
    personal: true,
    skills: [...personalSkills],
    enforceClaude: false,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    ask: acceptAll,
    writeLine: () => undefined,
  });

  const read = (relativePath: string) =>
    Bun.file(path.join(setup.root, relativePath)).text();
  const manifest = JSON.parse(await read(".shadowclone/harness.json"));

  expect(manifest.gate.command).toBe("bun run check");
  expect(manifest.conventions).toEqual(
    expect.arrayContaining([
      { kind: "file-length", maximumLines: 200 },
      { kind: "no-comments", language: "typescript" },
      { kind: "forbidden-text", name: "em-dash", text: "\u2014" },
      { kind: "no-suppressions" },
    ]),
  );

  const agents = await read("AGENTS.md");

  for (const skill of personalSkills) {
    const original = await repositoryText(`skills/${skill}/SKILL.md`);

    expect(await read(`.claude/skills/${skill}/SKILL.md`)).toBe(original);
    expect(await read(`.agents/skills/${skill}/SKILL.md`)).toBe(original);
    expect(agents).toContain(
      `- \`${skill}\`: ${original.match(/^description: '(.+)'$/m)?.[1]?.replaceAll("''", "'")}`,
    );
  }

  expect(agents).toContain(
    "- `feature-workflow`: Use before any feature, fix, or refactor",
  );
  expect(agents).toContain(
    "- Gate: `bun run check`. Run it before presenting any change.",
  );
  expect(await read("CLAUDE.md")).toContain("\n@AGENTS.md\n");
  expect(await read(".claude/skills/feature-workflow/SKILL.md")).toContain(
    "6. Run `bun run check` and fix every failure.",
  );
});
