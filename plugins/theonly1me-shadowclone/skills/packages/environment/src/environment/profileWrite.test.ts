import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { parseProfileRules, profileRulePath } from "@shadowclone/profile";
import type { ProfileRule } from "@shadowclone/profile";
import { writeProfile } from "./profileRecords";

async function createTestPaths(): Promise<ProjectPaths> {
  const homeDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-profile-"),
  );

  return createProjectPaths({ homeDirectory, platform: "darwin" });
}

function profileRule(observations: number): ProfileRule {
  return {
    key: "rule-one",
    title: "Runs focused checks",
    body: "Run the narrow check before the full suite.",
    section: "workflow",
    scope: "org",
    originDirectory: "github.com--acme--936913df4a5c268b",
    repositoryName: null,
    source: "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: ["event:one"], against: [] },
    observations,
    lastSeen: "2026-09-05",
    sessions: 2,
    origins: ["github.com/acme"],
    importReference: null,
  };
}

test("preserves a hand-edited rule verbatim", async () => {
  const paths = await createTestPaths();
  const first = profileRule(2);

  await writeProfile({ paths, rules: [first] });

  const filePath = path.join(paths.profileDirectory, profileRulePath(first));
  const original = await Bun.file(filePath).text();
  const edited = original.replace(
    "Run the narrow check before the full suite.",
    "Run only the checks that prove the requested behavior.",
  );

  await Bun.write(filePath, edited);

  await writeProfile({ paths, rules: [profileRule(9)] });

  const regenerated = await Bun.file(filePath).text();

  expect(regenerated).toBe(edited);
  expect(regenerated).toContain('"observations":2');
});

test("preserves a rule the user added without generated metadata", async () => {
  const paths = await createTestPaths();
  const rule = profileRule(2);

  await writeProfile({ paths, rules: [rule] });

  const filePath = path.join(paths.profileDirectory, profileRulePath(rule));
  const manual = "## Keep reviews short\n\nWrite the result first.";

  await Bun.write(filePath, `${await Bun.file(filePath).text()}\n${manual}\n`);

  await writeProfile({ paths, rules: [profileRule(3)] });

  expect(await Bun.file(filePath).text()).toContain(manual);
});

test("keeps generated rules that were not part of the current write", async () => {
  const paths = await createTestPaths();
  const first = profileRule(2);
  const second: ProfileRule = {
    ...first,
    key: "rule-two",
    title: "Review the diff",
  };

  await writeProfile({ paths, rules: [first, second] });

  await writeProfile({ paths, rules: [first] });

  const filePath = path.join(paths.profileDirectory, profileRulePath(first));

  expect(await Bun.file(filePath).text()).toContain(second.title);
});

test("drops in-flight duplicate rules with the same key", async () => {
  const paths = await createTestPaths();

  await writeProfile({ paths, rules: [profileRule(1), profileRule(2)] });

  const filePath = path.join(
    paths.profileDirectory,
    profileRulePath(profileRule(1)),
  );
  const matches = (await Bun.file(filePath).text()).match(
    /Runs focused checks/g,
  );

  expect(matches).toHaveLength(1);
});

test("updates reconciliation metadata without replacing user-edited wording", async () => {
  const paths = await createTestPaths();
  const initial = profileRule(2);

  await writeProfile({ paths, rules: [initial] });

  const filePath = path.join(paths.profileDirectory, profileRulePath(initial));
  const userBody = "Run the checks that directly prove the requested behavior.";

  await Bun.write(
    filePath,
    (await Bun.file(filePath).text()).replace(initial.body, userBody),
  );

  const [edited] = parseProfileRules(await Bun.file(filePath).text());

  if (!edited) {
    throw new Error("Expected the edited profile rule");
  }

  const reconciled: ProfileRule = {
    ...initial,
    title: edited.title,
    body: edited.body,
    source: "user",
    status: "active",
    proposal: {
      kind: "narrow",
      text: "Limit the rule\n\nRun focused checks for code changes only.",
    },
    evidence: { for: initial.evidence.for, against: ["event:two"] },
  };

  await writeProfile({ paths, rules: [reconciled] });

  const text = await Bun.file(filePath).text();
  const [stored] = parseProfileRules(text);

  expect(text).toContain(userBody);
  expect(stored?.source).toBe("user");
  expect(stored?.proposal).toEqual(reconciled.proposal);
  expect(stored?.evidence.against).toEqual(["event:two"]);
});
