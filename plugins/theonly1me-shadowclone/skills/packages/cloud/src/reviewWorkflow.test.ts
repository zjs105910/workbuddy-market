import { expect, test } from "bun:test";
import { fixtureClone } from "./fixtures";
import { cloneFromRelay } from "./installed";
import { renderWorkflows } from "./workflow";

type Job = { readonly steps?: readonly Record<string, unknown>[]; readonly environment?: string; readonly needs?: unknown };

function jobs(): Readonly<Record<string, Job>> {
  const worker = renderWorkflows(fixtureClone)[".github/workflows/shadowclone.yml"] ?? "";
  const parsed: unknown = Bun.YAML.parse(worker);

  if (typeof parsed !== "object" || parsed === null || !("jobs" in parsed)) {
    throw new Error("The worker workflow has no jobs");
  }

  const { jobs: rendered } = parsed;

  if (typeof rendered !== "object" || rendered === null) {
    throw new Error("The worker jobs are not a map");
  }

  return Object.fromEntries(Object.entries(rendered));
}

test("the job that runs the pull request's toolchain gets no secrets and no environment", () => {
  const checks = jobs()["review-checks"];

  expect(checks).toBeDefined();
  expect(checks?.environment).toBeUndefined();
  expect(JSON.stringify(checks)).not.toContain("secrets.");
});

test("the model job holds only the Claude token and the publish job alone holds the App key", () => {
  const rendered = jobs();
  const analyze = JSON.stringify(rendered["review-analyze"]);
  const publish = JSON.stringify(rendered["review-publish"]);

  expect(analyze).toContain("secrets.CLAUDE_CODE_OAUTH_TOKEN");
  expect(analyze).not.toContain("SHADOWCLONE_APP_PRIVATE_KEY");
  expect(publish).toContain("SHADOWCLONE_APP_PRIVATE_KEY");
  expect(publish).not.toContain("CLAUDE_CODE_OAUTH_TOKEN");
});

test("review requests skip the work job", () => {
  const work = renderWorkflows(fixtureClone)[".github/workflows/shadowclone.yml"] ?? "";

  expect(work).toContain("if: needs.guard.outputs.allowed == 'true' && needs.guard.outputs.kind != 'review'");
});

test("the update path reads the clone configuration back from the installed relay", () => {
  const relay = renderWorkflows(fixtureClone)[".github/workflows/shadowclone-relay.yml"] ?? "";

  expect(cloneFromRelay(relay)).toEqual(fixtureClone);
});
