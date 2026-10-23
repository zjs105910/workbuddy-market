import { readEffectiveConfig, projectPaths, type ProjectPaths } from "@shadowclone/core";
import {
  pendingLearningRecords,
  readIntegrations,
  readRedactedEnvironment,
  recordFingerprint,
} from "@shadowclone/environment";
import { readPendingLearning } from "@shadowclone/learning";

export async function showHome(options: {
  readonly paths?: ProjectPaths;
  readonly writeLine?: (line: string) => void;
} = {}): Promise<void> {
  const paths = options.paths ?? projectPaths;
  const writeLine = options.writeLine ?? console.log;

  if (!(await Bun.file(paths.configFile).exists())) {
    writeLine("Shadowclone is not set up. Run shadowclone init to choose what it may read and install guidance.");

    return;
  }

  const [{ config }, state, pending, integrations] = await Promise.all([
    readEffectiveConfig({ configPath: paths.configFile, managedConfigPath: paths.managedConfigFile }),
    readRedactedEnvironment(paths),
    readPendingLearning(paths),
    readIntegrations(paths),
  ]);
  const active = state?.records.filter((record) =>
    record.rule.status === "active" && record.rule.proposal === null &&
    state.dispositions.some((entry) => entry.key === record.rule.key &&
      entry.inputFingerprint === recordFingerprint(record) &&
      (entry.status === "published" || entry.status === "covered")),
  ).length ?? 0;
  const awaitingPublication = state === null
    ? 0 : pendingLearningRecords({ paths, state }).length;

  writeLine(`Shadowclone: ${active} active learned rule(s), ${pending.rules.length} awaiting review, ${awaitingPublication} awaiting scope or publication, ${integrations.length} agent installation(s).`);
  writeLine(pending.rules.length > 0
    ? "Next: shadowclone learning pending"
    : awaitingPublication > 0
      ? "Next: shadowclone learning pending"
      : config.distillation.deep && active === 0
        ? "Next: shadowclone learn --deep"
        : integrations.length === 0
          ? "Next: shadowclone install --agent claude-code|codex --global"
          : "Next: start a new agent session to load active guidance. Run shadowclone learning status for the latest attempt.");
}
