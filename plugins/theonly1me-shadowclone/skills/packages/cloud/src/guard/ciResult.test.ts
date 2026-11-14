import { expect, test } from "bun:test";
import { resolveTrigger } from "./events";
import { eventContext, fixtureClone, fixtureIssue, fixturePull, githubFixture } from "../fixtures";

function cloneCiRoutes(options: { readonly runningWorkflows: readonly string[] }) {
  return {
    "GET /repos/sample/project/actions/runs/50": {
      status: "completed",
      conclusion: "success",
      head_repository: { id: fixtureClone.repositoryId },
      path: ".github/workflows/ci.yml",
      head_branch: fixturePull.head.ref,
      head_sha: fixturePull.head.sha,
      actor: { login: fixtureClone.botLogin },
      run_attempt: 1,
    },
    "GET /repos/sample/project/actions/runs": {
      workflow_runs: [
        { id: 50, status: "completed", path: ".github/workflows/ci.yml" },
        ...options.runningWorkflows.map((workflow, index) => ({
          id: 60 + index,
          status: "in_progress",
          path: `.github/workflows/${workflow}`,
        })),
      ],
    },
    "GET /repos/sample/project/pulls": [fixturePull],
    "GET /repos/sample/project/pulls/2": fixturePull,
    "GET /repos/sample/project/issues/1": fixtureIssue,
  };
}

const cloneCiResult = eventContext({
  event: "workflow_run",
  actor: fixtureClone.botLogin,
  payload: { workflow_run: { id: 50 } },
});

test("CI on the clone's own push resumes its PR once every workflow on the head finished", async () => {
  const { request } = githubFixture(cloneCiRoutes({ runningWorkflows: [] }));
  const trigger = await resolveTrigger({ clone: fixtureClone, context: cloneCiResult, request });

  expect(trigger?.kind).toBe("pull");
  expect(trigger?.branch).toBe(fixturePull.head.ref);
  expect(trigger?.head).toBe(fixturePull.head.sha);
});

test("a CI result waits while another workflow on the same head is still running", async () => {
  const { request } = githubFixture(
    cloneCiRoutes({ runningWorkflows: ["plugin-security-scan.yml"] }),
  );

  expect(await resolveTrigger({ clone: fixtureClone, context: cloneCiResult, request })).toBeNull();
});
