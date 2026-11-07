export type ProfileSection = "engineering" | "workflow" | "boundaries";

export type ProfileScope = "global" | "org" | "project";

export type ProfileSource = "declared" | "imported" | "mined" | "user";

export type ProfileStatus = "active" | "candidate" | "stale";

export type ProfileProposalKind = "revise" | "narrow" | "retire";

export type ProfileProposal = {
  readonly kind: ProfileProposalKind;
  readonly text: string;
};

export type ProfileEvidence = {
  readonly for: readonly string[];
  readonly against: readonly string[];
};

export type ProfileImportReference = {
  readonly repositoryAliases: readonly string[];
  readonly sourceLocator: string;
};

type ProfileRuleLocation =
  | {
      readonly scope: "global";
      readonly originDirectory: null;
      readonly repositoryName: null;
    }
  | {
      readonly scope: "org";
      readonly originDirectory: string;
      readonly repositoryName: null;
    }
  | {
      readonly scope: "project";
      readonly originDirectory: string;
      readonly repositoryName: string;
    };

type ProfileRuleFields = {
  readonly key: string;
  readonly title: string;
  readonly body: string;
  readonly section: ProfileSection;
  readonly source: ProfileSource;
  readonly status: ProfileStatus;
  readonly proposal: ProfileProposal | null;
  readonly appliesWhen: readonly string[];
  readonly evidence: ProfileEvidence;
  readonly observations: number;
  readonly lastSeen: string;
  readonly sessions: number;
  readonly origins: readonly string[];
  readonly importReference: ProfileImportReference | null;
};

export type ProfileRule = ProfileRuleFields & ProfileRuleLocation;

export type ExistingProfileRule = {
  readonly key: string;
  readonly title: string;
  readonly body: string;
  readonly source: ProfileSource;
  readonly status: ProfileStatus;
  readonly proposal: ProfileProposal | null;
  readonly appliesWhen: readonly string[];
  readonly evidence: ProfileEvidence;
  readonly observations: number;
  readonly lastSeen: string;
  readonly sessions: number;
  readonly origins: readonly string[];
  readonly scope: ProfileScope;
  readonly importReference: ProfileImportReference | null;
  readonly fingerprint: string;
  readonly content: string;
  readonly edited: boolean;
  readonly legacy: boolean;
};

export type ExistingProfileBlock =
  | ExistingProfileRule
  | {
      readonly key: null;
      readonly content: string;
      readonly edited: true;
      readonly source: "user";
      readonly status: "active";
    };

export type ProfileRuleReference = {
  readonly relativePath: string;
  readonly key: string;
};

export type ProfileWriteResult = {
  readonly files: number;
  readonly rules: number;
  readonly rejected: number;
  readonly preserved: number;
};
