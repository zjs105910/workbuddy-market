import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import type {
  ExistingProfileRule,
  ProfileRule,
  ProfileRuleReference,
  ProfileWriteResult,
} from "@shadowclone/profile";
import { parseProfileRules, readGeneratedProfileState, profileRulePath } from "@shadowclone/profile";
import { readEnvironment } from "./store";
import { seedGuidanceProfileKey } from "@shadowclone/skills";
import type { SeedGuidance, SeedLibrary } from "@shadowclone/skills";
import { writeProfile } from "./profileRecords";

function profileBodyFromSeedGuidance(guidance: SeedGuidance): string {
  return guidance.kind === "skill"
    ? guidance.body.replace(/^## /gm, "### ")
    : guidance.body;
}

export function profileRuleFromSeedGuidance(
  guidance: SeedGuidance,
): ProfileRule {
  return {
    key: seedGuidanceProfileKey(guidance.id),
    title: guidance.title,
    body: profileBodyFromSeedGuidance(guidance),
    section: guidance.section,
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "declared",
    status: "active",
    proposal: null,
    appliesWhen: guidance.appliesWhen,
    evidence: { for: [], against: [] },
    observations: 0,
    lastSeen: "declared",
    sessions: 0,
    origins: [],
    importReference: null,
  };
}

async function existingRulesByKey(options: {
  readonly paths: ProjectPaths;
  readonly relativePaths: readonly string[];
}): Promise<ReadonlyMap<string, ExistingProfileRule>> {
  const rules = new Map<string, ExistingProfileRule>();

  for (const relativePath of new Set(options.relativePaths)) {
    const file = Bun.file(
      path.join(options.paths.profileDirectory, relativePath),
    );

    if (!(await file.exists())) {
      continue;
    }

    for (const rule of parseProfileRules(await file.text())) {
      rules.set(rule.key, rule);
    }
  }

  return rules;
}

export async function writeSeedGuidanceSelection(options: {
  readonly paths: ProjectPaths;
  readonly library: SeedLibrary;
  readonly selectedGuidance: readonly SeedGuidance[];
}): Promise<ProfileWriteResult> {
  const selectedKeys = new Set(
    options.selectedGuidance.map((entry) => seedGuidanceProfileKey(entry.id)),
  );

  const libraryByKey = new Map(
    options.library.guidance.map((entry) => [
      seedGuidanceProfileKey(entry.id),
      entry,
    ]),
  );

  const environment = await readEnvironment(options.paths);

  if (environment) {
    const previous = environment.records.map(({ rule }) => rule);

    const rules = options.selectedGuidance.map((guidance) => {
      const selected = profileRuleFromSeedGuidance(guidance);
      const current = previous.find((rule) => rule.key === selected.key);

      return current &&
        (current.source === "user" || current.body !== selected.body)
        ? current
        : selected;
    });

    const retired = previous
      .filter((rule) => {
        const guidance = libraryByKey.get(rule.key);

        return (
          guidance &&
          !selectedKeys.has(rule.key) &&
          rule.source === "declared" &&
          rule.body === profileBodyFromSeedGuidance(guidance)
        );
      })
      .map((rule) => ({ key: rule.key, relativePath: profileRulePath(rule) }));

    return writeProfile({ paths: options.paths, rules, retired });
  }

  const previous = (
    await readGeneratedProfileState(options.paths.profileManifestFile)
  ).filter(
    (entry) =>
      entry.disposition === "present" &&
      entry.source === "declared" &&
      libraryByKey.has(entry.key),
  );

  const existing = await existingRulesByKey({
    paths: options.paths,
    relativePaths: previous.map((entry) => entry.relativePath),
  });
  const rules = options.selectedGuidance.map(profileRuleFromSeedGuidance);
  const retired: ProfileRuleReference[] = [];

  for (const entry of previous) {
    if (selectedKeys.has(entry.key)) {
      continue;
    }

    const guidance = libraryByKey.get(entry.key);

    if (!guidance) {
      continue;
    }

    const current = existing.get(entry.key);

    if (!current) {
      rules.push(profileRuleFromSeedGuidance(guidance));

      continue;
    }

    if (current.edited || current.source === "user") {
      continue;
    }

    retired.push({ relativePath: entry.relativePath, key: entry.key });
  }

  return writeProfile({ paths: options.paths, rules, retired });
}
