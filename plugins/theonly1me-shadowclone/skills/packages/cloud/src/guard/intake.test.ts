import { expect, test } from "bun:test";
import { resolveTrigger } from "./events";
import { eventContext, fixtureAccountClone, fixtureClone, fixtureIssue, fixturePull, githubFixture } from "../fixtures";

const issueRoute = "GET /repos/sample/project/issues/1";

test("an owner issue survives the default-branch relay dispatch", async () => {
  const { request } = githubFixture({ [issueRoute]: fixtureIssue });
  const direct = await resolveTrigger({ clone: fixtureClone, context: eventContext(), request });

  expect(direct?.kind).toBe("issue");

  const dispatch = eventContext({
    event: "workflow_dispatch",
    actor: "github-actions[bot]",
    payload: { inputs: { ...direct, action: "opened", identifier: "1", entity: "1" } },
  });
  const resolved = await resolveTrigger({ clone: fixtureClone, context: dispatch, request });

  expect(resolved).toEqual(direct);
  expect(resolved?.actor).toBe("sample");
});

test("an owner issue survives a relay dispatch when GitHub leaves out the empty head input", async () => {
  const { request } = githubFixture({ [issueRoute]: fixtureIssue });
  const direct = await resolveTrigger({ clone: fixtureClone, context: eventContext(), request });
  const dispatch = eventContext({
    event: "workflow_dispatch",
    actor: "github-actions[bot]",
    payload: {
      inputs: {
        source: "issues",
        action: "opened",
        identifier: "1",
        entity: "1",
        branch: "shadowclone/issue-1",
        key: direct?.key,
      },
    },
  });

  expect(direct?.head).toBe("");
  expect(await resolveTrigger({ clone: fixtureClone, context: dispatch, request })).toEqual(direct);
});

test("outsider issues and relays with changed repository IDs fail closed", async () => {
  const { request } = githubFixture({
    [issueRoute]: { ...fixtureIssue, user: { login: "outside" } },
  });

  expect(
    await resolveTrigger({ clone: fixtureClone, context: eventContext(), request }),
  ).toBeNull();
  expect(
    await resolveTrigger({
      clone: fixtureClone,
      context: eventContext({ payload: { repository: { id: 999 } } }),
      request,
    }),
  ).toBeNull();
});

test("an owner can tag the default alias or the named clone", async () => {
  for (const body of ["@shadowclone update the parser", "@sample-clone: update the parser"]) {
    const { request } = githubFixture({
      [issueRoute]: fixtureIssue,
      "GET /repos/sample/project/issues/comments/4": {
        user: { login: "sample", type: "User" },
        body,
        issue_url: "https://api.github.com/repos/sample/project/issues/1",
        updated_at: "synthetic-version",
      },
    });
    const context = eventContext({ event: "issue_comment", payload: { comment: { id: 4 } } });

    expect((await resolveTrigger({ clone: fixtureClone, context, request }))?.key).toBe(
      "issue_comment:4:synthetic-version",
    );
  }
});

test("a machine account bot answers to its own login and not to the shadowclone alias", async () => {
  const keys: (string | null)[] = [];

  for (const body of ["@sample-shadow update the parser", "@shadowclone update the parser"]) {
    const { request } = githubFixture({
      [issueRoute]: fixtureIssue,
      "GET /repos/sample/project/issues/comments/4": {
        user: { login: "sample", type: "User" },
        body,
        issue_url: "https://api.github.com/repos/sample/project/issues/1",
        updated_at: "synthetic-version",
      },
    });
    const context = eventContext({ event: "issue_comment", payload: { comment: { id: 4 } } });

    keys.push((await resolveTrigger({ clone: fixtureAccountClone, context, request }))?.key ?? null);
  }

  expect(keys).toEqual(["issue_comment:4:synthetic-version", null]);
});

test("tag requests reject foreign authors, the clone itself, and forks", async () => {
  for (const user of [
    { login: "outside", type: "User" },
    { login: fixtureClone.botLogin, type: "Bot" },
    { login: "sample", type: "User" },
  ]) {
    const { request } = githubFixture({
      "GET /repos/sample/project/issues/comments/4": {
        user,
        body: "@shadowclone do work",
        issue_url: "https://api.github.com/repos/sample/project/issues/2",
        updated_at: "v1",
      },
      "GET /repos/sample/project/issues/2": {
        ...fixtureIssue,
        number: 2,
        pull_request: { url: "synthetic" },
      },
      "GET /repos/sample/project/pulls/2": {
        ...fixturePull,
        head: { ...fixturePull.head, repo: { id: 999 } },
      },
    });
    const context = eventContext({
      event: "issue_comment",
      actor: user.login,
      payload: { comment: { id: 4 } },
    });

    expect(await resolveTrigger({ clone: fixtureClone, context, request })).toBeNull();
  }
});

test("a paused issue rejects work, and forged dispatch inputs cannot change branches", async () => {
  const { request } = githubFixture({
    [issueRoute]: { ...fixtureIssue, labels: [{ name: "shadowclone:paused" }] },
  });

  expect(
    await resolveTrigger({ clone: fixtureClone, context: eventContext(), request }),
  ).toBeNull();

  const unpaused = githubFixture({ [issueRoute]: fixtureIssue });
  const context = eventContext({
    event: "workflow_dispatch",
    payload: {
      inputs: {
        source: "issues",
        action: "opened",
        identifier: "1",
        entity: "1",
        branch: "main",
        head: "",
        key: "issues:1:",
      },
    },
  });

  expect(
    await resolveTrigger({ clone: fixtureClone, context, request: unpaused.request }),
  ).toBeNull();
});
