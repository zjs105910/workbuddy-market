import { readEffectiveConfig, projectPaths } from "@shadowclone/core";

export async function authorizeStudy(options: { readonly configPath?: string; readonly managedConfigPath?: string | null } = {}): Promise<void> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.configPath ?? projectPaths.configFile,
    managedConfigPath: options.managedConfigPath === undefined ? projectPaths.managedConfigFile : options.managedConfigPath,
  });
  const sources = ["agent-context", "skill-library", "claude-code"] as const;

  if (!policy.enabled || policy.distillation !== "allowed" || !config.distillation.deep ||
    sources.some((source) => !config.sources[source] || !policy.allowedSources.includes(source))) {
    throw new Error("The preference study requires enabled agent-context, skill-library, and session sources, deep learning, and permitting managed policy");
  }
}
