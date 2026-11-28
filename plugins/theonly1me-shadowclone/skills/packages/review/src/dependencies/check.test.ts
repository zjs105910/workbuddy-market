import { expect, test } from "bun:test";
import { collectReview } from "../collect";
import { createGitFixture } from "../collect/gitFixture";
import { checkDependencies } from "./index";
import type { JsonRequest } from "./osv";

async function lockfileChange() {
  const fixture = await createGitFixture();
  const lock = (lodash: string) =>
    JSON.stringify({ lockfileVersion: 3, packages: { "": {}, "node_modules/lodash": { version: lodash }, "node_modules/left-pad": { version: "1.3.0" } } }, null, 2);
  await fixture.write({ "package-lock.json": lock("4.17.21") });
  const baseSha = fixture.commit("base");
  await fixture.write({ "package-lock.json": lock("4.17.20") });
  const headSha = fixture.commit("head");
  const context = await collectReview({
    checkout: fixture.directory,
    facts: { repository: "example/app", number: 1, title: "t", body: "", baseRefName: "main", baseSha, headSha },
  });

  return { checkout: fixture.directory, baseSha, headSha, files: context.files };
}

function osv(calls: string[]): JsonRequest {
  return async ({ url, body }) => {
    calls.push(body === undefined ? url : `${url} ${JSON.stringify(body)}`);

    if (url.endsWith("/querybatch")) {
      return { results: [{ vulns: [{ id: "GHSA-test-0001" }] }] };
    }

    return {
      id: "GHSA-test-0001",
      summary: "Prototype pollution in zipObjectDeep",
      database_specific: { severity: "HIGH" },
      affected: [{ package: { name: "lodash", ecosystem: "npm" }, ranges: [{ events: [{ introduced: "0" }, { fixed: "4.17.21" }] }] }],
    };
  };
}

test("an added vulnerable dependency becomes a certain finding on its lockfile line", async () => {
  const calls: string[] = [];
  const check = await checkDependencies({ ...(await lockfileChange()), network: true, request: osv(calls) });

  expect(check.hits.map((hit) => [hit.ruleId, hit.level, hit.severity, hit.path, hit.line, hit.title])).toEqual([
    ["GHSA-test-0001", "certain", "high", "package-lock.json", 6, "Known vulnerability in lodash@4.17.20"],
  ]);
  expect(check.hits[0]?.failure).toBe("GHSA-test-0001 (high): Prototype pollution in zipObjectDeep. Fixed versions: 4.17.21.");
});

test("only packages that the change adds or upgrades are sent to OSV", async () => {
  const calls: string[] = [];

  await checkDependencies({ ...(await lockfileChange()), network: true, request: osv(calls) });

  expect(calls[0]).toContain('"name":"lodash"');
  expect(calls[0]).not.toContain("left-pad");
});

test("with the network off, nothing is sent and the report says why", async () => {
  const calls: string[] = [];
  const check = await checkDependencies({ ...(await lockfileChange()), network: false, request: osv(calls) });

  expect([calls, check.hits, check.reports[0]?.status]).toEqual([[], [], "skipped"]);
});

test("an OSV outage is reported as a failed check, not as a clean result", async () => {
  const check = await checkDependencies({
    ...(await lockfileChange()),
    network: true,
    request: async () => {
      throw new Error("OSV returned 503");
    },
  });

  expect([check.reports[0]?.status, check.reports[0]?.detail]).toEqual(["failed", "OSV could not be read: OSV returned 503"]);
});
