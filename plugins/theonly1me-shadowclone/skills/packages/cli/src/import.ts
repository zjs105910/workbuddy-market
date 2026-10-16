import {
  readConfig,
  readManagedPolicy,
  setSourceEnabled,
  writeConfig,
  type ProjectPaths,
  projectPaths,
} from "@shadowclone/core";
import type { ManagedPolicy } from "@shadowclone/core";
import {
  importRepositoryGuidance,
  type RepositoryGuidanceImportResult,
} from "@shadowclone/learning";
import { refreshIntegrations } from "@shadowclone/environment";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { promptConfirmation, type ConfirmPrompt } from "./confirm";

export async function importRepositoryGuidanceCommand(
  options: {
    readonly configPath?: string;
    readonly paths?: ProjectPaths;
    readonly workingDirectory?: string;
    readonly managedConfigPath?: string | null;
    readonly managedPolicy?: ManagedPolicy;
    readonly readRemote?: GitRemoteReader;
    readonly ask?: ConfirmPrompt;
    readonly writeLine?: (line: string) => void;
  } = {},
): Promise<RepositoryGuidanceImportResult | null> {
  const paths = options.paths ?? projectPaths;
  const configPath = options.configPath ?? paths.configFile;
  const policy =
    options.managedPolicy ??
    (await readManagedPolicy(
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
    ));

  if (!policy.enabled) {
    throw new Error("Shadowclone is disabled by managed policy");
  }

  if (!policy.allowedSources.includes("declared-rules")) {
    throw new Error("Managed policy blocks repository guidance import");
  }

  let config = await readConfig({ configPath });

  if (!config.sources["declared-rules"]) {
    const ask = options.ask ?? promptConfirmation;

    if (!(await ask("Import existing repository guidance?"))) {
      return null;
    }

    config = setSourceEnabled({
      config,
      source: "declared-rules",
      enabled: true,
    });
    await writeConfig({ config, configPath });
  }

  const result = await importRepositoryGuidance({
    paths,
    workingDirectory: options.workingDirectory ?? process.cwd(),
    gitMetadataEnabled:
      config.sources["git-metadata"] &&
      policy.allowedSources.includes("git-metadata"),
    blockedOrigins: policy.blockedOrigins,
    readRemote: options.readRemote,
  });
  const writeLine = options.writeLine ?? ((line) => console.log(line));

  await refreshIntegrations({
    paths,
    configPath,
    managedConfigPath: options.managedConfigPath,
    readRemote: options.readRemote,
  });
  writeLine(
    `Imported ${result.imported} repository guidance files; ${result.preserved} preserved; ${result.rejected} rejected; ${result.retired} retired.`,
  );

  return result;
}
