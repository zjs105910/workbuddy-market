import type { OriginScope } from "@shadowclone/sessions";
import type { ProfileRule, ProfileSource, ProfileStatus } from "../types";

export type ProfileCompilationAudience = "main" | "subagent";

export type ProfileCompilationRepositoryContext = "native" | "missing";

export type ProfileCompilationFormat = "full" | "index" | "harness";

export type ProfileCompilationSource = ProfileSource | "reference";

export type ProfileCompileInput =
  | {
      readonly kind: "directory";
      readonly profileDirectory: string;
      readonly origin: OriginScope | null;
      readonly targetRepo: string | null;
      readonly scope?: "global" | "scoped" | "combined";
    }
  | {
      readonly kind: "rules";
      readonly rules: readonly ProfileRule[];
    };

export type ProfileCompilationOmissionReason =
  | "candidate"
  | "stale"
  | "axis-conflict"
  | "native-duplicate"
  | "known-duplicate"
  | "in-harness"
  | "not-applicable"
  | "on-demand"
  | "budget";

export type ProfileCompilationOmission = {
  readonly ruleKey: string | null;
  readonly referenceKey?: string;
  readonly reason: ProfileCompilationOmissionReason;
};

export type ProfileCompilationBreakdown = {
  readonly source: ProfileCompilationSource;
  readonly appliedCount: number;
  readonly omittedCount: number;
  readonly appliedBytes: number;
};

export type ProfileCompilation = {
  readonly markdown: string;
  readonly appliedRuleKeys: readonly string[];
  readonly appliedRuleCount: number;
  readonly appliedReferenceKeys: readonly string[];
  readonly appliedReferenceCount: number;
  readonly usedBytes: number;
  readonly byteBudget: number;
  readonly breakdown: readonly ProfileCompilationBreakdown[];
  readonly omissions: readonly ProfileCompilationOmission[];
};

type CompilerBlockFields = {
  readonly scope?: "global" | "org" | "project";
  readonly status: ProfileStatus;
  readonly observations: number;
  readonly visible: string;
  readonly appliesWhen: readonly string[];
};

export type CompilerBlock =
  | (CompilerBlockFields & {
      readonly kind: "rule";
      readonly ruleKey: string | null;
      readonly referenceKey: null;
      readonly source: ProfileSource;
    })
  | (CompilerBlockFields & {
      readonly kind: "reference";
      readonly ruleKey: null;
      readonly referenceKey: string;
      readonly source: "reference";
      readonly status: "active";
    });
