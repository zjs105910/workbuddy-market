import { expect, test } from "bun:test";
import { eventContext, fixtureClone, fixtureIssue, githubFixture } from "../fixtures";
import { resolveTrigger } from "./events";

const ownerPull = {
  number: 2,
  state: "open",
  draft: false,
  user: { login: "sample" },
  head: { ref: "feature/total", sha: "b".repeat(40), repo: { id: fixtureClone.repositoryId } },
  labels: [],
};

function commentOnPull(body: string) {
  return githubFixture({
    "GET /repos/sample/project/issues/comments/4": {
      user: { login: "sample", type: "User" },
      body,
      issue_url: "https://api.github.com/repos/sample/project/issues/2",
      updated_at: "v1",
    },
    "GET /repos/sample/project/issues/2": { ...fixtureIssue, number: 2, pull_request: { url: "synthetic" } },
    "GET /repos/sample/project/pulls/2": ownerPull,
  });
}

const commentContext = eventContext({ event: "issue_comment", payload: { comment: { id: 4 } } });

test("a first-line review command on a pull request starts a review, not work", async () => {
  const { request } = commentOnPull("@shadowclone review\nThe totals changed.");

  const trigger = await resolveTrigger({ clone: fixtureClone, context: commentContext, request });

  expect([trigger?.kind, trigger?.entity, trigger?.head]).toEqual(["review", 2, "b".repeat(40)]);
});

test("any other tagged request on a pull request still starts work", async () => {
  const { request } = commentOnPull("@shadowclone review the totals and fix them");

  expect((await resolveTrigger({ clone: fixtureClone, context: commentContext, request }))?.kind).toBe("pull");
});

test("a review command on an issue starts nothing", async () => {
  const { request } = githubFixture({
    "GET /repos/sample/project/issues/comments/4": {
      user: { login: "sample", type: "User" },
      body: "@shadowclone review",
      issue_url: "https://api.github.com/repos/sample/project/issues/1",
      updated_at: "v1",
    },
    "GET /repos/sample/project/issues/1": fixtureIssue,
  });

  expect(await resolveTrigger({ clone: fixtureClone, context: commentContext, request })).toBeNull();
});

function openedContext(action: string) {
  return eventContext({
    event: "pull_request_target",
    payload: { action, pull_request: { number: 2 }, issue: undefined },
  });
}

function openedFixture(pull: Record<string, unknown>) {
  return githubFixture({
    "GET /repos/sample/project/pulls/2": pull,
    "GET /repos/sample/project/issues/2": { ...fixtureIssue, number: 2, pull_request: { url: "synthetic" } },
  });
}

test("a requester's pull request starts a review when it opens or becomes ready", async () => {
  for (const action of ["opened", "ready_for_review"]) {
    const { request } = openedFixture(ownerPull);

    const trigger = await resolveTrigger({ clone: fixtureClone, context: openedContext(action), request });

    expect([trigger?.kind, trigger?.key]).toEqual(["review", `pull_request_target:2:${"b".repeat(40)}`]);
  }
});

test("drafts, outside authors, the clone's own pull requests, and forks start no automatic review", async () => {
  for (const pull of [
    { ...ownerPull, draft: true },
    { ...ownerPull, user: { login: "outside" } },
    { ...ownerPull, user: { login: fixtureClone.botLogin } },
    { ...ownerPull, head: { ...ownerPull.head, repo: { id: 999 } } },
  ]) {
    const { request } = openedFixture(pull);

    expect(await resolveTrigger({ clone: fixtureClone, context: openedContext("opened"), request })).toBeNull();
  }
});
