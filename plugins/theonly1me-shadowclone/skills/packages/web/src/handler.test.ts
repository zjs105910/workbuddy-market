import { expect, test } from "bun:test";
import { buildInput } from "@shadowclone/builds/testing";
import { readEnvironment } from "@shadowclone/environment";
import { browserFixture, syntheticBrief } from "./fixtures";
import { applyResultSchema, buildViewSchema, previewSchema } from "./protocol";

test("the editor rejects missing tokens, foreign origins, and arbitrary writes", async () => {
  const fixture = await browserFixture();
  const handler = fixture.createHandler();
  const absentToken = new Request(`${fixture.origin}/api/build`);
  const foreign = fixture.request({
    path: "/api/skill/preview",
    body: syntheticBrief,
  });

  foreign.headers.set("Origin", "https://example.invalid");

  expect((await handler(absentToken)).status).toBe(403);
  expect((await handler(foreign)).status).toBe(403);
  expect(
    (
      await handler(
        fixture.request({
          path: "/api/preview",
          body: {
            ...buildInput(),
            filePath: "../../outside",
            content: "changed",
          },
        }),
      )
    ).status,
  ).toBe(400);
  expect(fixture.calls).toHaveLength(0);
  expect(await readEnvironment(fixture.context.paths)).toBeNull();
});

test("reviewed changes apply once and remain undoable after reopening the editor", async () => {
  const fixture = await browserFixture();
  const handler = fixture.createHandler();
  const preview = await handler(
    fixture.request({ path: "/api/preview", body: buildInput() }),
  );
  const review = previewSchema.parse(await preview.json());

  expect(review.changes.length).toBeGreaterThan(0);
  expect(await readEnvironment(fixture.context.paths)).toBeNull();

  const apply = () =>
    fixture.request({ path: "/api/apply", body: { previewId: review.id } });
  const applied = applyResultSchema.parse(
    await (await handler(apply())).json(),
  );

  expect(applied.revisionId).not.toBeNull();
  expect((await handler(apply())).status).toBe(400);

  const reopened = fixture.createHandler();
  const view = buildViewSchema.parse(
    await (
      await reopened(fixture.request({ path: "/api/build?scope=global" }))
    ).json(),
  );

  expect(view.revisionId).toBe(applied.revisionId);
  expect(view.input.choices["tests-that-catch-bugs"]).toBe(true);

  const undone = await reopened(
    fixture.request({
      path: "/api/undo",
      body: { revisionId: view.revisionId },
    }),
  );

  expect(undone.status).toBe(200);
  expect(await readEnvironment(fixture.context.paths)).toBeNull();
  expect(fixture.calls).toHaveLength(0);
});
