import { expect, test } from "bun:test";
import path from "node:path";
import { createRequire } from "node:module";
import { renderWorkflows, actionPins } from "./workflow";
import {
  fixtureClone,
  guidanceFixture,
  eventContext,
  fixtureIssue,
  githubFixture,
} from "./fixtures";
import { record } from "./guard/records";
import { reactToRequest } from "./react";

test(
  "rendered workflows pin actions and restrict credentials to a validated " + "repository worker",
  () => {
    const files = renderWorkflows(fixtureClone);
    const relay = files[".github/workflows/shadowclone-relay.yml"] ?? "";
    const worker = files[".github/workflows/shadowclone.yml"] ?? "";

    expect(relay).not.toContain("secrets.");
    expect(relay).toContain("ref: config.defaultBranch");
    expect(relay).toContain("pull_request_target:");
    expect(worker).toContain("environment: shadowclone");
    expect(worker).toContain("github.ref == 'refs/heads/main'");
    expect(worker).toContain("repositories: 'project'");
    expect(worker.indexOf("allowWorker")).toBeLessThan(
      worker.indexOf("secrets.SHADOWCLONE_APP_PRIVATE_KEY"),
    );
    expect(worker).toContain("timeout-minutes: 180");
    expect(worker).toContain("timeout-minutes: 170");
    expect(worker).not.toContain("--max-turns");
    expect(worker).toContain("show_full_output: false");
    expect(worker).toContain("--permission-mode acceptEdits --allowedTools Bash,Skill");
    expect(worker).toContain("Never push to the default branch.");

    for (const action of Object.values(actionPins)) {
      expect(action).toMatch(/@[a-f0-9]{40}$/);
      expect(relay + worker).toContain(action);
    }
  },
);

test("generated CommonJS guards execute with the same owner issue policy", async () => {
  const fixture = await guidanceFixture();

  try {
    for (const [file, content] of Object.entries(renderWorkflows(fixtureClone))) {
      await Bun.write(path.join(fixture.root, file), content);
    }

    const require = createRequire(import.meta.url);
    const module = record(require(path.join(fixture.root, ".github/shadowclone/guard/events.cjs")));
    const resolve = module.resolveTrigger;

    if (typeof resolve !== "function") {
      throw new Error("The generated guard does not export its policy.");
    }

    const { request } = githubFixture({ "GET /repos/sample/project/issues/1": fixtureIssue });
    const result: unknown = await resolve({
      clone: fixtureClone,
      context: eventContext(),
      request,
    });

    expect(record(result).branch).toBe("shadowclone/issue-1");
  } finally {
    await fixture.cleanup();
  }
});

test("the worker prompt authorizes the clone to mark its own PR ready for review", () => {
  const worker = renderWorkflows(fixtureClone)[".github/workflows/shadowclone.yml"] ?? "";

  expect(worker).toContain(
    "Every request authorizes marking a PR that the clone opened ready for review",
  );
});

test("the worker reacts to the request before it checks out the skills", () => {
  const worker = renderWorkflows(fixtureClone)[".github/workflows/shadowclone.yml"] ?? "";

  expect(worker).toContain("reactToRequest");
  expect(worker.indexOf("reactToRequest")).toBeLessThan(worker.indexOf("SHADOWCLONE_SKILLS_KEY"));
});

test("the clone reacts with eyes to the comment or issue that started the work", async () => {
  const reactions = {
    "POST /repos/sample/project/issues/1/reactions": {},
    "POST /repos/sample/project/issues/comments/7/reactions": {},
    "POST /repos/sample/project/pulls/comments/8/reactions": {},
  };
  const expected: Record<string, string | null> = {
    issues: "POST /repos/sample/project/issues/1/reactions",
    issue_comment: "POST /repos/sample/project/issues/comments/7/reactions",
    pull_request_review_comment: "POST /repos/sample/project/pulls/comments/8/reactions",
    pull_request_review: null,
    workflow_run: null,
  };

  for (const [source, route] of Object.entries(expected)) {
    const { request, calls } = githubFixture(reactions);
    const identifier = source === "pull_request_review_comment" ? 8 : 7;

    await reactToRequest({
      repository: "sample/project",
      source,
      identifier,
      entity: 1,
      request,
      warn: () => {},
    });

    expect(calls).toEqual(route ? [{ route, parameters: { content: "eyes" } }] : []);
  }
});

test("a failed reaction warns and lets the work continue", async () => {
  const { request } = githubFixture({});
  const warnings: string[] = [];

  await reactToRequest({
    repository: "sample/project",
    source: "issues",
    identifier: 1,
    entity: 1,
    request,
    warn: (message) => warnings.push(message),
  });

  expect(warnings).toHaveLength(1);
});
