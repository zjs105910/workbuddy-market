import { expect, test } from "bun:test";
import { listRevisions } from "@shadowclone/changes";
import { compileContext } from "@shadowclone/environment";
import { integrationFixture } from "@shadowclone/core/testing";
import { rememberPreference } from "./index";

test("explicit preferences are active, scoped and reversible without inference", async () => {
  const setup = await integrationFixture();
  const key = await rememberPreference({
    ...setup,
    text: "Prefer composition for extension points.",
    scope: "repository",
  });

  expect(key).toStartWith("declared-");
  expect(await compileContext(setup)).toContain(
    "## Prefer composition for extension points",
  );
  expect(
    await compileContext({ ...setup, cwd: `${setup.cwd}-other` }),
  ).not.toContain("Prefer composition");
  expect(await listRevisions(setup.paths)).toHaveLength(1);
});

test("long explicit preferences use a complete clause as their heading", async () => {
  const setup = await integrationFixture();

  await rememberPreference({
    ...setup,
    text: "Before committing or pushing, stop and ask the maintainer to review the completed diff, with a proposed one-line commit message. Do not commit.",
    scope: "global",
  });

  expect(await compileContext(setup)).toContain(
    "## Before committing or pushing, stop and ask the maintainer to review the completed diff\n",
  );
});

test("explicit preferences escape both HTML comment closing forms", async () => {
  const setup = await integrationFixture();

  await rememberPreference({
    ...setup,
    text: "Preserve literal examples: <!-- ordinary --> and <!-- alternate --!>.",
    scope: "global",
  });

  const context = await compileContext(setup);

  expect(context).toContain("&lt;!-- ordinary --&gt;");
  expect(context).toContain("&lt;!-- alternate --!&gt;");
  expect(context).not.toContain("--!>");
});
