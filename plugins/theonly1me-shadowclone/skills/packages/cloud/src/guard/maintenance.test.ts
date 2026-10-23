import { expect, test } from "bun:test";
import { resolveTrigger } from "./events";
import { eventContext, fixtureClone, fixtureIssue, fixturePull, githubFixture } from "../fixtures";
import { allowWorker, cancelBranchWork } from "./policy";

function reviewRoutes(pull: Record<string, unknown> = fixturePull) {
  return {
    "GET /repos/sample/project/pulls/comments/4": {
      user: { login: "reviewer[bot]", type: "Bot" },
      body: "Fix this field",
      pull_request_url: "https://api.github.com/repos/sample/project/pulls/2",
      updated_at: "v1",
    },
    "GET /repos/sample/project/issues/2": {
      ...fixtureIssue,
      number: 2,
      pull_request: { url: "synthetic" },
    },
    "GET /repos/sample/project/pulls/2": pull,
    "GET /repos/sample/project/issues/1": fixtureIssue,
  };
}

test("an allowed reviewer resumes only a managed same-repository PR", async () => {
  const context = eventContext({
    event: "pull_request_review_comment",
    actor: "reviewer[bot]",
    payload: { comment: { id: 4 } },
  });
  const managed = githubFixture(reviewRoutes());

  expect(
    (await resolveTrigger({ clone: fixtureClone, context, request: managed.request }))?.kind,
  ).toBe("pull");

  const unmanaged = githubFixture(reviewRoutes({ ...fixturePull, user: { id: 90 } }));

  expect(
    await resolveTrigger({ clone: fixtureClone, context, request: unmanaged.request }),
  ).toBeNull();
});

test("CI must refer to the current head and cannot replay the clone workflows", async () => {
  for (const [head, workflow] of [
    ["a".repeat(40), "ci.yml"],
    ["b".repeat(40), "ci.yml"],
    ["a".repeat(40), "shadowclone.yml"],
  ]) {
    const { request } = githubFixture({
      "GET /repos/sample/project/actions/runs/50": {
        status: "completed",
        conclusion: "failure",
        head_repository: { id: 10 },
        path: `.github/workflows/${workflow}`,
        head_branch: fixturePull.head.ref,
        head_sha: head,
        actor: { login: "sample" },
        run_attempt: 1,
      },
      "GET /repos/sample/project/actions/runs": { workflow_runs: [] },
      "GET /repos/sample/project/pulls": [fixturePull],
      "GET /repos/sample/project/pulls/2": fixturePull,
      "GET /repos/sample/project/issues/1": fixtureIssue,
    });
    const context = eventContext({ event: "workflow_run", payload: { workflow_run: { id: 50 } } });
    const result = await resolveTrigger({ clone: fixtureClone, context, request });

    expect(result !== null).toBe(head === fixturePull.head.sha && workflow === "ci.yml");
  }
});

test("a PR pause event cancels only that branch's active clone runs", async () => {
  const { request, calls } = githubFixture({
    "GET /repos/sample/project/issues/2/events": [
      {
        id: 80,
        event: "labeled",
        label: { name: "shadowclone:paused" },
        actor: { login: "sample" },
      },
    ],
    "GET /repos/sample/project/issues/2": {
      ...fixtureIssue,
      number: 2,
      pull_request: { url: "synthetic" },
      labels: [{ name: "shadowclone:paused" }],
    },
    "GET /repos/sample/project/pulls/2": {
      ...fixturePull,
      labels: [{ name: "shadowclone:paused" }],
    },
    "GET /repos/sample/project/actions/workflows/shadowclone.yml/runs": {
      workflow_runs: [
        {
          id: 90,
          status: "in_progress",
          display_title: "Shadowclone shadowclone/issue-1 [issues:1:]",
        },
        {
          id: 91,
          status: "in_progress",
          display_title: "Shadowclone shadowclone/issue-3 [issues:3:]",
        },
      ],
    },
    "POST /repos/sample/project/actions/runs/90/cancel": {},
  });
  const context = eventContext({
    event: "pull_request_target",
    payload: {
      issue: undefined,
      pull_request: { number: 2 },
      action: "labeled",
      label: { name: "shadowclone:paused" },
    },
  });
  const trigger = await resolveTrigger({ clone: fixtureClone, context, request });

  expect(trigger?.kind).toBe("pause");
  await cancelBranchWork({ clone: fixtureClone, request, branch: trigger?.branch ?? "" });
  expect(calls.filter((call) => call.route.startsWith("POST"))).toEqual([
    { route: "POST /repos/sample/project/actions/runs/90/cancel", parameters: undefined },
  ]);
});

test("duplicate events and the daily branch budget prevent a worker", async () => {
  const trigger = {
    source: "issues",
    identifier: 1,
    entity: 1,
    actor: "sample",
    branch: "shadowclone/issue-1",
    head: "",
    key: "issues:1:",
    kind: "issue" as const,
  };

  for (const runs of [
    [{ id: 90, display_title: "Shadowclone shadowclone/issue-1 [issues:1:]" }],
    Array.from({ length: 10 }, (_, index) => ({
      id: index + 50,
      display_title: `Shadowclone shadowclone/issue-1 [event:${index}]`,
    })),
  ]) {
    const { request } = githubFixture({
      "GET /repos/sample/project/actions/workflows/shadowclone.yml/runs": { workflow_runs: runs },
    });

    expect(
      await allowWorker({ clone: fixtureClone, context: eventContext(), request, trigger }),
    ).toBeFalse();
  }
});

test("an approved reviewer bot can maintain a PR through an issue comment", async () => {
  const routes = reviewRoutes();
  const { request } = githubFixture({
    ...routes,
    "GET /repos/sample/project/issues/comments/5": {
      user: { login: "reviewer[bot]", type: "Bot" },
      body: "The parser needs a correction.",
      issue_url: "https://api.github.com/repos/sample/project/issues/2",
      updated_at: "v2",
    },
  });
  const context = eventContext({
    event: "issue_comment",
    actor: "reviewer[bot]",
    payload: { comment: { id: 5 } },
  });

  expect((await resolveTrigger({ clone: fixtureClone, context, request }))?.kind).toBe("pull");
});
