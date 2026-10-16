import {
  readEffectiveConfig,
  type ManagedPolicy,
  type ShadowcloneConfig,
} from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { initialize } from "./init";
import { offerNativeUpgrade } from "./nativeUpgrade";

export async function prepareManualLearning(options: {
  readonly paths: ProjectPaths;
  readonly configPath: string;
  readonly initializationConfigPath?: string;
  readonly managedConfigPath?: string | null;
  readonly writeLine: (line: string) => void;
}): Promise<{
  readonly config: ShadowcloneConfig;
  readonly policy: ManagedPolicy;
}> {
  const { paths, configPath, writeLine } = options;

  if (!(await Bun.file(configPath).exists())) {
    if (!process.stdin.isTTY) {
      throw new Error(
        "No configuration found. Run shadowclone init interactively first.",
      );
    }

    writeLine("No configuration found. Running shadowclone init...");
    await initialize({ configPath: options.initializationConfigPath });
  }

  const { config, policy } = await readEffectiveConfig({
    configPath,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled) {
    throw new Error("Shadowclone is disabled by managed policy");
  }

  if (process.stdin.isTTY && process.env.SHADOWCLONE_INTERNAL_RUN !== "1") {
    await offerNativeUpgrade({ paths });
  }

  return { config, policy };
}
