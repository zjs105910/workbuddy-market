import type { CompiledContext } from "@shadowclone/environment";

export type ContextExplanation = {
  readonly budget: { readonly usedBytes: number; readonly limitBytes: number };
  readonly applied: { readonly rules: number; readonly references: number };
  readonly breakdown: CompiledContext["compilation"]["breakdown"];
  readonly omissions: CompiledContext["compilation"]["omissions"];
  readonly scopeFiles: readonly string[];
  readonly referenceRoots: readonly string[];
  readonly referenceUsage: {
    readonly applied: number;
    readonly omitted: number;
  };
  readonly isolatedRules: number;
  readonly legacyRules: number;
};

export function explainContext(context: CompiledContext): ContextExplanation {
  const reference = context.compilation.breakdown.find(
    (entry) => entry.source === "reference",
  );

  return {
    budget: {
      usedBytes: context.compilation.usedBytes,
      limitBytes: context.compilation.byteBudget,
    },
    applied: {
      rules: context.compilation.appliedRuleCount,
      references: context.compilation.appliedReferenceCount,
    },
    breakdown: context.compilation.breakdown,
    omissions: context.compilation.omissions,
    scopeFiles: context.scopeFiles,
    referenceRoots: context.referenceRoots,
    referenceUsage: {
      applied: reference?.appliedCount ?? 0,
      omitted: reference?.omittedCount ?? 0,
    },
    isolatedRules: context.diagnostics.isolatedRules,
    legacyRules: context.diagnostics.legacyRules,
  };
}

export function renderStartupContextSummary(
  context: CompiledContext | null,
): string {
  if (context === null) {
    return "Session-start context: disabled by policy.";
  }

  const { compilation } = context;
  const omitted = new Map<string, number>();

  for (const omission of compilation.omissions) {
    omitted.set(omission.reason, (omitted.get(omission.reason) ?? 0) + 1);
  }

  const reasons =
    [...omitted].map(([reason, count]) => `${count} ${reason}`).join(", ") ||
    "none";

  return `Session-start context here: ${compilation.appliedRuleCount} rule line(s), ${compilation.usedBytes}/${compilation.byteBudget} bytes; omitted: ${reasons}.`;
}

export function renderContextExplanation(
  explanation: ContextExplanation,
): string {
  const lines = [
    `Budget: ${explanation.budget.usedBytes}/${explanation.budget.limitBytes} bytes`,
    `Applied: ${explanation.applied.rules} rule(s), ${explanation.applied.references} reference(s)`,
    "Sources:",
    ...explanation.breakdown.map(
      (entry) =>
        `  ${entry.source}: ${entry.appliedCount} applied, ${entry.omittedCount} omitted, ${entry.appliedBytes} bytes`,
    ),
    `Omissions: ${explanation.omissions.length}`,
    ...explanation.omissions.map(
      (entry) =>
        `  ${entry.referenceKey ?? entry.ruleKey ?? "manual-block"}: ${entry.reason}`,
    ),
    `Scope files: ${explanation.scopeFiles.join(", ") || "none"}`,
    `Reference roots: ${explanation.referenceRoots.join(", ") || "none"}`,
    `Isolated rules: ${explanation.isolatedRules}`,
    `Legacy rules: ${explanation.legacyRules}`,
  ];

  return `${lines.join("\n")}\n`;
}
