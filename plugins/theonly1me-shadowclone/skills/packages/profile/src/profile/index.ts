export { renderAgent, writeAgent } from "./agent";

export {
  compileProfile,
  defaultIndexByteBudget,
  defaultProfileByteBudget,
  profileScopePaths,
  toolPatterns,
  type KnownTool,
  type ProfileCompilation,
  type ProfileCompilationAudience,
  type ProfileCompilationBreakdown,
  type ProfileCompilationFormat,
  type ProfileCompilationOmission,
  type ProfileCompilationOmissionReason,
  type ProfileCompilationRepositoryContext,
  type ProfileCompileInput,
  type RepositoryApplicability,
} from "./compiler";

export {
  activatesFromSessions,
  effectiveProfileStatus,
  independentSessionThreshold,
  parseProfileEvidenceId,
  explicitProfileEvidence,
  isExplicitProfileEvidence,
  profileEvidenceId,
  profileEvidenceStatistics,
} from "./evidence";

export { renderMirror } from "./mirror";

export { readProfileDiagnostics, type ProfileDiagnostics } from "./diagnostics";

export { parseProfileBlocks, parseProfileRules } from "./parse";

export {
  readLegacyProfileSnapshot,
  type ProfileSnapshot,
  type ProfileSnapshotRejection,
  type ProfileSnapshotRule,
} from "./snapshot";

export {
  createProfileRuleKey,
  profileFingerprint,
  profileRulePath,
  renderProfileRule,
} from "./render";

export { mergeProfileImportReference } from "./importReference";

export type {
  ExistingProfileRule,
  ExistingProfileBlock,
  ProfileEvidence,
  ProfileImportReference,
  ProfileProposal,
  ProfileProposalKind,
  ProfileRule,
  ProfileRuleReference,
  ProfileScope,
  ProfileSection,
  ProfileSource,
  ProfileStatus,
  ProfileWriteResult,
} from "./types";

export { writeLegacyProfile, type ProfileWriteOptions } from "./write";

export {
  applyProfileCuration,
  applyProfileRepair,
  createProfileCurationPlan,
  createProfileRepairPlan,
  parseProfileCurationDecisions,
  type BlockedOriginRepair,
  type OriginRepair,
  type ProfileCurationDecision,
  type ProfileCurationDecisions,
  type ProfileCurationPlan,
  type ProfileRepairPlan,
} from "./repair";

export {
  readGeneratedProfileState,
  parseProfileRejectionText,
  readProfileRejections,
} from "./state";

export type {
  GeneratedProfileStateEntry,
  ProfileRejection,
  ProfileRejectionReason,
} from "./state";

export { splitProfileBlocks } from "./blocks";

export { renderGeneratedProfileState, renderProfileRejections } from "./stateRender";

export { profileVisibleParts, stripProfileMetadata } from "./visible";
