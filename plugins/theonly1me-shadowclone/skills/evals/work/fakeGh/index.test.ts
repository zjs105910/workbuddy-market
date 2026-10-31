import { expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { standardJobs } from "../scaffold/project";
import { commitAndPush, createWorkspace, gh, sampleCase, stateOf } from "./testCase";

test("reports failing checks, then passes after a rerun of a flaky job", () => {
  const root = createWorkspace(sampleCase({ jobs: standardJobs.map((job) => (job.name === "lint" ? { ...job, flakyFailures: 1 } : job)) }));
  const first = gh({ root, args: ["pr", "checks", "7"] });

  expect(first.exitCode).toBe(1);
  expect(first.stdout).toContain("lint\tfail");
  expect(first.stdout).toContain("test\tpass");

  const failed = stateOf(root).runs.find((run) => run.job === "lint");

  gh({ root, args: ["run", "rerun", String(failed?.id), "--failed"] });

  const second = gh({ root, args: ["pr", "checks", "7", "--json", "name,bucket", "--jq", "map(.bucket) | unique | join(\",\")"] });

  expect(second.stdout.trim()).toBe("pass");
});

test("records replies and resolutions through REST and GraphQL", () => {
  const root = createWorkspace(sampleCase({}));
  const listed = gh({ root, args: ["api", "repos/{owner}/{repo}/pulls/7/comments", "--jq", ".[].user.type"] });

  expect(listed.stdout.trim()).toBe("Bot");

  gh({ root, args: ["api", "-X", "POST", "repos/acme/ledger/pulls/7/comments/1000/replies", "-f", "body=abc1234"] });
  gh({ root, args: ["api", "graphql", "-f", "query=mutation($threadId: ID!) { resolveReviewThread(input: {threadId: $threadId}) { thread { isResolved } } }", "-f", "threadId=PRRT_bot"] });

  const [thread] = stateOf(root).threads;

  expect(thread?.comments.map((comment) => comment.body)).toEqual(["Handle an empty list.", "abc1234"]);
  expect(thread?.resolved).toBeTrue();
});

test("lists review threads through GraphQL with author types", () => {
  const root = createWorkspace(sampleCase({}));
  const result = gh({
    root,
    args: ["api", "graphql", "-F", "number=7", "-f", "query=query($number: Int!) { repository(owner: \"acme\", name: \"ledger\") { pullRequest(number: $number) { reviewThreads(first: 50) { nodes { id isResolved comments(first: 5) { nodes { author { __typename } body } } } } } } }", "--jq", ".data.repository.pullRequest.reviewThreads.nodes[] | .id"],
  });

  expect(result.stdout.trim()).toBe("PRRT_bot");
});

test("releases a delayed bot comment after the head changes and records top-level comments", () => {
  const root = createWorkspace(sampleCase({}));

  commitAndPush({ root, branch: "feature", files: { "ledger/total.py": "def total(values: list[int]) -> int:\n    return sum(values or [])\n" } });
  gh({ root, args: ["pr", "comment", "7", "--body", "Good call, fixed!"] });

  const state = stateOf(root);

  expect(state.threads.map((thread) => thread.released)).toEqual([true, true]);
  expect(state.topLevelComments.map((comment) => comment.body)).toEqual(["Good call, fixed!"]);
});

test("marks a pull request ready and logs the checks it saw", () => {
  const root = createWorkspace(sampleCase({}));

  gh({ root, args: ["pr", "ready", "7"] });

  const log = readFileSync(path.join(root, ".fake-gh", "log.jsonl"), "utf8").trim().split("\n");
  const ready = log.map((line) => JSON.parse(line)).find((entry) => entry.operation === "pr-ready");

  expect(stateOf(root).pullRequests[0]?.draft).toBeFalse();
  expect(ready?.details.checks).toBe("success");
});

test("rejects unsupported commands and logs them", () => {
  const root = createWorkspace(sampleCase({}));
  const result = gh({ root, args: ["codespace", "list"] });

  expect(result.exitCode).toBe(1);
  expect(result.supported).toBeFalse();
  expect(result.stderr).toContain("does not support");
});

test("applies every operation in a batched GraphQL mutation", () => {
  const root = createWorkspace(sampleCase({}));
  const result = gh({
    root,
    args: ["api", "graphql", "-f", "query=mutation{a:addPullRequestReviewThreadReply(input:{pullRequestReviewThreadId:\"PRRT_bot\",body:\"abc1234\"}){comment{id}} b:resolveReviewThread(input:{threadId:\"PRRT_bot\"}){thread{isResolved}}}"],
  });
  const [thread] = stateOf(root).threads;

  expect(result.exitCode).toBe(0);
  expect(thread?.comments.map((comment) => comment.body)).toEqual(["Handle an empty list.", "abc1234"]);
  expect(thread?.resolved).toBeTrue();
});
