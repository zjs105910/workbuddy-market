import { expect, test } from "bun:test";
import { branchRepositoryName, hasUncommittedChanges, readBranchFacts } from "./branch";
import { createGitFixture } from "./gitFixture";

async function branchFixture() {
  const fixture = await createGitFixture();
  await fixture.write({ "src/order.ts": "export const total = 1;\n" });
  const baseSha = fixture.commit("Add the order total");
  Bun.spawnSync(["git", "checkout", "--quiet", "-b", "discount"], { cwd: fixture.directory });

  return { fixture, baseSha };
}

test("a branch review starts at the merge base and takes one commit's subject and body", async () => {
  const { fixture, baseSha } = await branchFixture();
  await fixture.write({ "src/order.ts": "export const total = 2;\n" });
  const headSha = fixture.commit("Apply the discount\n\nCoupons now reduce the total.");

  const facts = await readBranchFacts({ checkout: fixture.directory, repository: "local/project", base: "main" });

  expect(facts).toEqual({
    repository: "local/project",
    number: null,
    title: "Apply the discount",
    body: "Coupons now reduce the total.",
    baseRefName: "main",
    baseSha,
    headSha,
  });
});

test("a branch with several commits keeps the latest subject and every message", async () => {
  const { fixture } = await branchFixture();
  await fixture.write({ "src/order.ts": "export const total = 2;\n" });
  fixture.commit("Apply the discount");
  await fixture.write({ "src/order.ts": "export const total = 3;\n" });
  fixture.commit("Round the total");

  const facts = await readBranchFacts({ checkout: fixture.directory, repository: "local/project", base: "main" });

  expect([facts.title, facts.body]).toEqual(["Round the total", "Round the total\n\nApply the discount"]);
});

test("a branch with no commits after its base, or an unknown base, is refused", async () => {
  const { fixture } = await branchFixture();

  await expect(readBranchFacts({ checkout: fixture.directory, repository: "local/project", base: "main" })).rejects.toThrow("no commits after main");
  await expect(readBranchFacts({ checkout: fixture.directory, repository: "local/project", base: "release" })).rejects.toThrow("cannot find the base release");
  await expect(readBranchFacts({ checkout: fixture.directory, repository: "local/project", base: null })).rejects.toThrow("no origin/HEAD");
});

test("the repository name comes from a GitHub origin, or from the folder", async () => {
  const { fixture } = await branchFixture();

  expect(await branchRepositoryName(fixture.directory)).toStartWith("local/shadowclone-review-test-");

  Bun.spawnSync(["git", "remote", "add", "origin", "git@github.com:example/project.git"], { cwd: fixture.directory });

  expect(await branchRepositoryName(fixture.directory)).toBe("example/project");
});

test("an untracked file counts as an uncommitted change", async () => {
  const { fixture } = await branchFixture();

  expect(await hasUncommittedChanges(fixture.directory)).toBe(false);

  await fixture.write({ "notes.txt": "draft\n" });

  expect(await hasUncommittedChanges(fixture.directory)).toBe(true);
});
