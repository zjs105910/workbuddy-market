import { learningRuleSchema, type LearningRecord } from "./types";

export function learningRecord(
  options: { readonly key?: string; readonly body?: string } = {},
): LearningRecord {
  return {
    kind: "guidance",
    sourceHash: null,
    sourceLocator: null,
    rule: learningRuleSchema.parse({
      key: options.key ?? "palette-validation",
      title: "Validate sample palette entries",
      body:
        options.body ??
        "Reject duplicate colors before writing the sample palette.",
      scope: "global",
      originDirectory: null,
      repositoryName: null,
      section: "workflow",
      source: "user",
      status: "active",
      proposal: null,
      appliesWhen: [],
      evidence: { for: [], against: [] },
      observations: 1,
      sessions: 1,
      lastSeen: "2026-01-01",
      origins: [],
      importReference: null,
    }),
  };
}
