import type { ProjectPaths } from "@shadowclone/core";
import { readEffectiveConfig } from "@shadowclone/core";

export async function assertCloudPolicy(options: {
  readonly paths: ProjectPaths;
  readonly engine: "claude" | "codex";
}): Promise<void> {
  const { policy } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath: options.paths.managedConfigFile,
  });
  const engine = options.engine === "codex" ? "codex" : "claude-code";

  if (!policy.enabled || !policy.allowedEngines.includes(engine) || policy.maxActionTier !== "act") {
    throw new Error(
      `Managed policy does not permit a ${options.engine === "codex" ? "Codex" : "Claude"} cloud bot with repository writes.`,
    );
  }
}
