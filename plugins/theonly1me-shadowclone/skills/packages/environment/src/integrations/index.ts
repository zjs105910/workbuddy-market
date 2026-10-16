export {
  compileContext,
  compileContextDetails,
  sessionStartProjection,
  type CompiledContext,
} from "./compile";
export { installIntegration, uninstallIntegration } from "./install";
export { nativeSessionEnd, nativeSessionStart } from "./hooks";
export { integrationHealth, refreshIntegrations } from "./refresh";
export { readIntegrations, saveIntegration } from "./state";
export {
  harnessMarkers,
  managedSection,
  managedStart,
  managedEnd,
  markedSection,
  type SectionMarkers,
  stripHarnessSection,
  stripManagedGuidance,
  updateManagedSection,
  updateMarkedSection,
} from "./markdown";
export {
  type Integration,
  type IntegrationAgent,
  integrationAgentSchema,
  type IntegrationOptions,
  type IntegrationScope,
  integrationScopeSchema,
} from "./types";

export { hostDiscovery, knownDeliveryGaps } from "./discovery";

export { prepareIntegrationFiles } from "./files";

export { HiddenInstructionsError } from "./hiddenInstructions";

export { ensureHookRunner } from "./hookRunner";

export { checkArtifactWrite, writeInstalledArtifact } from "./installation/artifactOwnership";

export {
  addGitExcludes,
  artifactExcludePatterns,
  artifactRelativePaths,
  removeArtifacts,
  removeGitExcludes,
} from "./installation/installArtifacts";

export {
  findInstallation,
  type InstalledArtifact,
  mergeInstallation,
  readInstallations,
  removeInstallation,
  writeInstallations,
} from "./installation/installState";

export { resolveInstallTarget } from "./installation/installTarget";

export { learningSessionKey } from "./sessionKey";

export { integrationFilePath } from "./targets";
