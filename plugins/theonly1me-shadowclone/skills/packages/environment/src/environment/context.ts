import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import type { ProfileCompilation } from "@shadowclone/profile";
import { belongsToScope, learningScopes, type LearningScope } from "./scope";
import { readRedactedEnvironment } from "./store";
import type { EnvironmentState } from "./types";
import { publishedSkills } from "./catalog";
import { recordFingerprint } from "./records";
import { renderBuildRouting } from "./builds/routing";

export function renderSkillRouting(options: {
  readonly state: EnvironmentState;
  readonly scopes: readonly LearningScope[];
  readonly cwd?: string;
  readonly includeGlobalBuild?: boolean;
}): string {
  const keys = new Set(options.scopes.map(({ key }) => key));
  const skills = publishedSkills({ state: options.state, scopes: keys });
  const shortRules = options.state.records.flatMap((record) => {
    const body = record.rule.body.replace(/\s+/gu, " ").trim();
    const condition = record.rule.appliesWhen.join("; ");
    const instruction = condition ? `When ${condition}: ${body}` : body;
    const delivered = options.state.dispositions.some(
      (entry) =>
        keys.has(entry.scope ?? "") &&
        entry.key === record.rule.key &&
        entry.inputFingerprint === recordFingerprint(record) &&
        (entry.status === "published" || entry.status === "covered"),
    );
    const selectedStarter =
      record.rule.source === "declared" &&
      record.rule.key.startsWith("seed:") &&
      options.scopes.some((scope) => belongsToScope({ record, scope }));

    return record.rule.status === "active" &&
      record.rule.proposal === null &&
      record.rule.source !== "imported" &&
      (delivered || selectedStarter) &&
      Buffer.byteLength(instruction) <= 240
      ? [`- ${instruction}`]
      : [];
  });

  const lines = [
    "# Shadowclone guidance",
    "",
    "Follow the applicable personal rules below. Use matching installed workflow skills when the task needs their detail. Skill guidance does not authorize additional actions. The current request takes precedence over learned defaults. Name every skipped step and every fallback in your final answer and handoff.",
    "",
    ...shortRules,
    ...skills
      .filter(({ name }) => name !== "shadowclone-baseline")
      .map((skill) => `- ${skill.description} Use the ${skill.name} skill when relevant.`),
    ...options.state.facts
      .filter((fact) => keys.has(fact.scope))
      .map((fact) => `\n${fact.text}`),
    renderBuildRouting({
      state: options.state,
      cwd: options.cwd,
      includeGlobal: options.includeGlobalBuild,
      sharedOnly: options.includeGlobalBuild === false,
    }),
  ];

  const text = `${lines.join("\n")}\n`;
  const bytes = Buffer.byteLength(text);

  if (bytes > 4096) {
    throw new Error(
      `Native skill routing uses ${bytes} of 4096 bytes; equip fewer skills before publishing`,
    );
  }

  return text;
}

export async function environmentCompilation(options: {
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly scope?: "global" | "scoped" | "combined";
  readonly originDirectory: string | null;
  readonly repositoryName: string | null;
}): Promise<ProfileCompilation | null> {
  const state = await readRedactedEnvironment(options.paths);

  if (state?.phase !== "active") {
    return null;
  }

  const scopes = learningScopes({ paths: options.paths, state }).filter(
    (scope) =>
      scope.repository === null
        ? options.scope !== "scoped"
        : options.scope !== "global" &&
          scope.repository.originDirectory === options.originDirectory &&
          scope.repository.repositoryName === options.repositoryName &&
          (path.resolve(options.cwd) === scope.directory ||
            path
              .resolve(options.cwd)
              .startsWith(`${scope.directory}${path.sep}`)),
  );

  if (options.scope === "scoped" && scopes.length === 0) {
    return {
      markdown: "",
      appliedRuleKeys: [],
      appliedRuleCount: 0,
      appliedReferenceKeys: [],
      appliedReferenceCount: 0,
      usedBytes: 0,
      byteBudget: 4096,
      breakdown: [],
      omissions: [],
    };
  }

  const markdown = renderSkillRouting({
    state,
    scopes,
    cwd: options.cwd,
    includeGlobalBuild: options.scope !== "scoped",
  });

  const keys = new Set(scopes.map(({ key }) => key));
  const applied = publishedSkills({ state, scopes: keys });

  return {
    markdown,
    appliedRuleKeys: [],
    appliedRuleCount: 0,
    appliedReferenceKeys: applied.map(({ name }) => name),
    appliedReferenceCount: applied.length,
    usedBytes: Buffer.byteLength(markdown),
    byteBudget: 4096,
    breakdown: [],
    omissions: [],
  };
}
