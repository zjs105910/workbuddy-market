import { expect, test } from "bun:test";
import { skillFixture } from "./testing";
import { learningSnapshot } from "./records";
import { writeEnvironment } from "./store";
import { emptyEnvironment } from "./types";

test("organization rejections keep their structure when learning text is redacted", async () => {
  const setup = await skillFixture();
  const rejection = {
    schema: 1, relativePath: "org/github.com--synthetic--9f3a7c21e4b8d605/projects/sample--1c2d3e4f5a6b7c8d.md", key: "mined:0123456789abcdef01234567",
    title: "Repository skill: Synthetic", body: "Use the synthetic workflow.", source: "mined", importReference: null, reason: "repo-covered",
  };
  await writeEnvironment({
    paths: setup.paths,
    state: { ...emptyEnvironment, phase: "active", automatic: true, rejectionText: `${JSON.stringify(rejection)}\n` },
  });

  const snapshot = await learningSnapshot(setup.paths);

  expect(snapshot?.rejections.map((entry) => entry.rejection.relativePath)).toEqual([rejection.relativePath]);
  expect(snapshot?.rejections[0]?.promptBody).toBe("Use the synthetic workflow.");
});
