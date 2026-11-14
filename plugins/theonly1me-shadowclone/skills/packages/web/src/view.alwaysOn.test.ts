import { expect, test } from "bun:test";
import { applyBuild, previewBuild } from "@shadowclone/builds";
import { buildInput } from "@shadowclone/builds/testing";
import { browserFixture } from "./fixtures";
import { buildViewSchema } from "./protocol";

test("the editor shows write-plain-english as locked and always on in every scope", async () => {
  const fixture = await browserFixture();
  const handler = fixture.createHandler();

  for (const scope of ["global", "private", "shared"]) {
    const view = buildViewSchema.parse(
      await (await handler(fixture.request({ path: `/api/build?scope=${scope}` }))).json(),
    );
    const item = view.items.find((candidate) => candidate.id === "write-plain-english");
    const other = view.items.find((candidate) => candidate.id === "tests-that-catch-bugs");

    expect(item?.alwaysOn).toBeTrue();
    expect(view.locked["write-plain-english"]).toBeTrue();
    expect(other?.alwaysOn).toBeFalse();
    expect(view.locked["tests-that-catch-bugs"]).toBeUndefined();
  }
});

test("the editor lists a shared requirement but not the always on skill under a shared build", async () => {
  const fixture = await browserFixture();
  const handler = fixture.createHandler();

  await applyBuild({
    ...fixture.context,
    plan: await previewBuild({
      ...fixture.context,
      input: buildInput({ scope: "shared", choices: { "tests-that-catch-bugs": true } }),
    }),
  });

  const view = buildViewSchema.parse(
    await (await handler(fixture.request({ path: "/api/build?scope=private" }))).json(),
  );

  expect(view.requirements).toContain("Shared requirement: Tests That Catch Bugs");
  expect(view.requirements).not.toContain("Shared requirement: Write Plain English");
  expect(view.locked["write-plain-english"]).toBeTrue();
});
