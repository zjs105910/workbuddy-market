import type { ProfileRejectionReason, ProfileSection } from "../../profile";

export type ClaudeMemoryKind =
  | "user"
  | "feedback"
  | "reference"
  | "project"
  | "index";

export type ClaudeMemoryFile = {
  readonly filename: string;
  readonly sourcePath: string;
  readonly kind: ClaudeMemoryKind;
  readonly hash: string;
  readonly bytes: number;
  readonly name: string;
  readonly description: string;
  readonly modified: string;
  readonly body: string;
};

export type ClaudeFeedbackDecision =
  | {
      readonly disposition: "rule";
      readonly title: string;
      readonly scope: "global" | "project";
      readonly section: ProfileSection;
    }
  | {
      readonly disposition: "rejected";
      readonly reason: ProfileRejectionReason;
    };

export type ClaudeMemoryDisposition =
  | "rule"
  | "reference"
  | "recall-reference"
  | "review-required"
  | "covered"
  | "project-preserved"
  | "index-rebuilt"
  | "archive-only";

export type ClaudeMemoryManifestFile = {
  readonly filename: string;
  readonly hash: string;
  readonly bytes: number;
  readonly kind: ClaudeMemoryKind;
  readonly disposition: ClaudeMemoryDisposition;
  readonly reason?: ProfileRejectionReason;
  readonly destination?: string;
};

export type ClaudeMemoryManifest = {
  readonly schema: 1;
  readonly repositoryId: string;
  readonly sourceDirectory: string;
  readonly createdAt: string;
  readonly files: readonly ClaudeMemoryManifestFile[];
};
