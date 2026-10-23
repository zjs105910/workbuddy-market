import { readEffectiveConfig, projectPaths } from "@shadowclone/core";
import {
  compileProfile,
  profileScopePaths,
  readProfileDiagnostics,
  type ProfileCompilation,
  type ProfileCompilationAudience,
  type ProfileCompilationFormat,
  type ProfileDiagnostics,
  type RepositoryApplicability,
  referenceScopeRoots,
} from "@shadowclone/profile";
import { isOriginBlocked, resolveRepository } from "@shadowclone/sessions";
import { committedHarnessRuleKeys } from "./harnessRules";
import { readClaudeRules } from "./claudeRules";
import { readNativeGuidance } from "./nativeGuidance";
import type { IntegrationOptions } from "./types";
import { environmentCompilation } from "../environment/context";

export type CompiledContext = {
  readonly compilation: ProfileCompilation;
  readonly scopeFiles: readonly string[];
  readonly referenceRoots: readonly string[];
  readonly diagnostics: ProfileDiagnostics;
};

type ContextOptions = IntegrationOptions & {
  readonly cwd: string;
  readonly scope?: "global" | "scoped" | "combined";
  readonly audience?: ProfileCompilationAudience;
  readonly format?: ProfileCompilationFormat;
  readonly nativeDuplicates?: "including-harness" | "excluding-harness" | false;
  readonly byteBudget?: number;
  readonly applicability?: RepositoryApplicability;
  readonly harnessRules?: boolean;
};

export const sessionStartProjection = {
  format: "index",
  nativeDuplicates: "including-harness",
  harnessRules: true,
} as const;

export async function compileContextDetails(
  options: ContextOptions,
): Promise<CompiledContext | null> {
  const paths = options.paths ?? projectPaths;
  const { config, policy } = await readEffectiveConfig({
    configPath: options.configPath ?? paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled) {
    return null;
  }

  const repository =
    options.scope === "global"
      ? null
      : await resolveRepository({
          cwd: options.cwd,
          enabled: config.sources["git-metadata"],
          readRemote: options.readRemote,
        });

  if (
    repository &&
    isOriginBlocked({ repository, patterns: policy.blockedOrigins })
  ) {
    return null;
  }

  const environment = await environmentCompilation({
    paths,
    cwd: options.cwd,
    scope: options.scope,
    originDirectory: repository?.origin.directoryName ?? null,
    repositoryName: repository?.profileFileName ?? null,
  });

  if (environment !== null) {
    return {
      compilation: environment,
      scopeFiles: ["environment.json"],
      referenceRoots: [],
      diagnostics: { isolatedRules: 0, legacyRules: 0 },
    };
  }

  const location = {
    origin: repository?.origin ?? null,
    targetRepo: repository?.profileFileName ?? null,
    scope: options.scope,
  };
  const knownNativeText = options.nativeDuplicates
    ? [
        ...(config.sources["declared-rules"]
          ? await readNativeGuidance({
              cwd: options.cwd,
              includeHarness: options.nativeDuplicates === "including-harness",
            })
          : []),
        ...(config.sources["claude-rules"]
          ? await readClaudeRules(options.cwd)
          : []),
      ]
    : [];
  const compilation = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory: paths.profileDirectory,
      ...location,
    },
    audience: options.audience,
    format: options.format,
    byteBudget: options.byteBudget,
    applicability: options.applicability,
    committedRuleKeys: options.harnessRules
      ? await committedHarnessRuleKeys(options.cwd)
      : undefined,
    knownNativeText,
  });

  return {
    compilation,
    scopeFiles: profileScopePaths(location),
    referenceRoots:
      options.audience === "subagent" ? [] : referenceScopeRoots(location),
    diagnostics: await readProfileDiagnostics(paths.profileDirectory),
  };
}

export async function compileContext(
  options: ContextOptions,
): Promise<string | null> {
  return (await compileContextDetails(options))?.compilation.markdown ?? null;
}
