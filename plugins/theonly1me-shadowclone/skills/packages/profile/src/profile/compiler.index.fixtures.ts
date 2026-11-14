import type { ProfileRule } from "./index";

export function rule(options: {
  readonly key: string;
  readonly title: string;
  readonly body: string;
  readonly appliesWhen?: readonly string[];
  readonly source?: ProfileRule["source"];
}): ProfileRule {
  return {
    key: options.key,
    title: options.title,
    body: options.body,
    section: "engineering",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: options.source ?? "mined",
    status: "active",
    proposal: null,
    appliesWhen: options.appliesWhen ?? [],
    evidence: { for: [], against: [] },
    observations: 1,
    lastSeen: "2026-09-26",
    sessions: 3,
    origins: [],
    importReference: null,
  };
}
