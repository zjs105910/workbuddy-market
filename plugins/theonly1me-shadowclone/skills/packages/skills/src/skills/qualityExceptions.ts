import type { SkillRule } from "./quality";

export const pendingSkillNames: ReadonlySet<string> = new Set();

export const permanentRuleExemptions: ReadonlyMap<string, readonly SkillRule[]> = new Map([
  ["shadowclone-work", ["gates", "example", "completion", "plain-english"]],
]);
