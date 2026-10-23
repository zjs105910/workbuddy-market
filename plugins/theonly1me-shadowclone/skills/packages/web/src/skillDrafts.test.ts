import { expect, test } from "bun:test";
import { readEnvironment } from "@shadowclone/environment";
import { buildFixture } from "@shadowclone/builds/testing";
import { createSkillDrafts } from "./skillDrafts";
import {
  skillDraftResultSchema,
  skillDraftReviewSchema,
} from "./skillDraftProtocol";
import {
  browserFixture,
  generationResult,
  syntheticBrief,
  syntheticSkill,
} from "./fixtures";

test("skill drafting reviews only redacted form text before a bounded call", async () => {
  const fixture = await browserFixture();
  const handler = fixture.createHandler();
  const secret = `sk-${"x".repeat(32)}`;
  const preview = await handler(
    fixture.request({
      path: "/api/skill/preview",
      body: {
        ...syntheticBrief,
        body: `${syntheticBrief.body} Token: ${secret}`,
      },
    }),
  );
  const review = skillDraftReviewSchema.parse(await preview.json());

  expect(preview.status).toBe(200);
  expect(fixture.calls).toHaveLength(0);
  expect(review.payload).toContain(syntheticBrief.body);
  expect(review.payload).not.toContain(secret);
  expect(review.payload).not.toContain(fixture.context.cwd);
  expect(review.limits).toContain("$0.25");

  const generated = await handler(
    fixture.request({
      path: "/api/skill/generate",
      body: { previewId: review.id },
    }),
  );

  expect(skillDraftResultSchema.parse(await generated.json()).skill).toEqual(
    syntheticSkill,
  );
  expect(fixture.calls).toHaveLength(1);
  expect(fixture.calls[0]).toMatchObject({
    prompt: review.payload,
    execution: { purpose: "learning" },
    allowedTools: [],
    permissionMode: "dontAsk",
    maxBudgetUsd: 0.25,
    outputSchema: { $schema: "http://json-schema.org/draft-07/schema#" },
  });
  expect(await readEnvironment(fixture.context.paths)).toBeNull();

  const duplicate = await handler(
    fixture.request({
      path: "/api/skill/generate",
      body: { previewId: review.id },
    }),
  );

  expect(duplicate.status).toBe(400);
  expect(fixture.calls).toHaveLength(1);
});

test("a canceled reviewed request never invokes the provider", async () => {
  const context = await buildFixture();
  let calls = 0;
  const drafts = createSkillDrafts({
    ...context,
    engine: {
      engine: "claude-code",
      runner: async () => {
        calls += 1;

        return generationResult(syntheticSkill);
      },
    },
  });
  const review = await drafts.preview(syntheticBrief);
  const controller = new AbortController();

  controller.abort();

  await expect(
    drafts.generate({ id: review.id, signal: controller.signal }),
  ).rejects.toThrow();
  expect(calls).toBe(0);
  expect(await readEnvironment(context.paths)).toBeNull();
});

test("malformed model output cannot publish a skill", async () => {
  const context = await buildFixture();
  const drafts = createSkillDrafts({
    ...context,
    engine: {
      engine: "claude-code",
      runner: async () =>
        generationResult({ name: "../outside", body: "draft" }),
    },
  });
  const review = await drafts.preview(syntheticBrief);

  await expect(drafts.generate({ id: review.id })).rejects.toThrow();
  expect(await readEnvironment(context.paths)).toBeNull();
});
