import type {
  ProfileRule,
  ProfileSnapshotRejection,
  ProfileSnapshotRule,
} from "@shadowclone/profile";
import type { CorrectionSignal } from "@shadowclone/sessions";
import type { DistillBatch } from "../batch";

export type ReconciliationVerdict = "reinforces" | "contradicts" | "narrows";

export type ReconciliationExistingRule = {
  readonly ruleToken: string;
  readonly verdict: ReconciliationVerdict;
  readonly observed: string;
  readonly evidenceTokens: readonly string[];
  readonly proposedTitle: string;
  readonly proposedBody: string;
  readonly axisChoiceToken: string;
};

export type ReconciliationNewRule = {
  readonly title: string;
  readonly body: string;
  readonly section: ProfileRule["section"];
  readonly observed: string;
  readonly evidenceTokens: readonly string[];
  readonly rejectionToken: string;
};

export type ReconciliationOutput = {
  readonly existingRules: readonly ReconciliationExistingRule[];
  readonly newRules: readonly ReconciliationNewRule[];
  readonly assessments?: readonly {
    readonly evidenceToken: string;
    readonly intent:
      | "preference"
      | "correction"
      | "approval"
      | "additional-context"
      | "cancellation"
      | "unknown";
    readonly durable: boolean;
    readonly explicit?: boolean;
    readonly scope: "global" | "repository";
  }[];
};

export type PromptAxisOption = {
  readonly token: string;
  readonly title: string;
  readonly body: string;
  readonly appliesWhen: readonly string[];
};

export type PromptRule = {
  readonly token: string;
  readonly snapshot: ProfileSnapshotRule;
  readonly axisOptions: readonly PromptAxisOption[];
};

export type PromptRejection = {
  readonly token: string;
  readonly snapshot: ProfileSnapshotRejection;
};

export type PromptEvidence = {
  readonly token: string;
  readonly evidenceId: string;
  readonly signal: CorrectionSignal;
};

export type ReconciliationContext = {
  readonly batch: DistillBatch;
  readonly rules: readonly PromptRule[];
  readonly rejections: readonly PromptRejection[];
  readonly evidence: readonly PromptEvidence[];
};

export type ReconciliationChange = {
  readonly kind: ReconciliationVerdict | "new" | "scope";
  readonly observed: string;
  readonly before: ProfileRule | null;
  readonly after: ProfileRule;
};

export type AppliedReconciliation = {
  readonly rules: readonly ProfileRule[];
  readonly changes: readonly ReconciliationChange[];
  readonly rejectedMatches: number;
};
