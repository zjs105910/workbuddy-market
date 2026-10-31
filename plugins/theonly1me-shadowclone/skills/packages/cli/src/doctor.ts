import {
  detectEngine,
  type CommandProbe,
  type EngineId,
  getProviderSupport,
  providerDefinitions,
} from "@shadowclone/agents";
import {
  readManagedPolicy,
  type DistillationPolicy,
  projectPaths,
  repairOwnedTree,
  readEffectiveConfig,
} from "@shadowclone/core";
import {
  openEventIndex,
  computeSourceHealth,
  type SourceMarkerHealth,
} from "@shadowclone/sessions";
import {
  compileContextDetails,
  environmentStatus,
  integrationHealth,
  sessionStartProjection,
} from "@shadowclone/environment";
import { readLearningState } from "@shadowclone/learning";
import { listSkillProposals, readMaintenanceState } from "@shadowclone/skills";
import { createProfileRepairPlan } from "@shadowclone/profile";
import { renderStartupContextSummary } from "./contextExplain";

export function renderProviderSupport(): readonly string[] {
  return providerDefinitions.map((definition) => {
    const support = getProviderSupport(definition);

    return `${definition.id}: observe=${support.observe ? "yes" : "no"}, distill=${
      support.distill ? "yes" : "no"
    }`;
  });
}

export function renderEngineSelection(options: {
  readonly distillation: DistillationPolicy;
  readonly selectedEngine: EngineId | null;
}): string {
  if (options.distillation === "disabled") {
    return "Deep distillation is disabled by managed policy.";
  }

  if (options.distillation === "local-only") {
    return "Deep distillation is restricted to local engines, which are not implemented.";
  }

  return options.selectedEngine
    ? `Selected engine: ${options.selectedEngine}`
    : "No authenticated distillation engine is available.";
}

export function renderMarkerHealth(options: {
  readonly health: readonly SourceMarkerHealth[];
}): readonly string[] {
  if (options.health.length === 0) {
    return ["No indexed sessions yet."];
  }

  return options.health.map((h) => {
    const status = h.isStale
      ? " (POSSIBLY STALE: 0 signals across 25+ sessions)"
      : "";

    return `${h.source}: ${h.sessions} sessions, ${h.interruptions} interruptions, ${h.denials} denials${status}`;
  });
}

export async function doctor(
  options: {
    readonly probe?: CommandProbe;
    readonly managedConfigPath?: string | null;
    readonly databasePath?: string;
    readonly shadowcloneDirectory?: string;
  } = {},
): Promise<void> {
  await repairOwnedTree(
    options.shadowcloneDirectory ?? projectPaths.shadowcloneDirectory,
  );

  const managedConfigPath =
    options.managedConfigPath === undefined
      ? projectPaths.managedConfigFile
      : options.managedConfigPath;
  const policy = await readManagedPolicy(managedConfigPath);

  if (
    managedConfigPath !== null &&
    (await Bun.file(managedConfigPath).exists())
  ) {
    console.log(`Managed policy: ${managedConfigPath}`);
  }

  if (!policy.enabled) {
    console.log("Managed policy: shadowclone is disabled.");

    return;
  }

  const allowedEngines =
    policy.distillation === "allowed" ? policy.allowedEngines : [];
  const { config } = await readEffectiveConfig({ managedConfigPath });
  const detection = await detectEngine({
    purpose: "distill",
    probe: options.probe,
    allowedEngines,
    preferredEngine: config.distillation.engine,
    model: config.distillation.model,
  });

  for (const engine of detection.availability) {
    const status = engine.authenticated
      ? "authenticated"
      : engine.installed
        ? "installed, authentication not found"
        : "not installed";

    console.log(`${engine.engine}: ${status}`);
  }

  console.log(
    renderEngineSelection({
      distillation: policy.distillation,
      selectedEngine: detection.selectedEngine,
    }),
  );
  console.log("Provider support:");

  for (const line of renderProviderSupport()) {
    console.log(line);
  }

  for (const line of await integrationHealth({ managedConfigPath })) {
    console.log(line);
  }

  console.log(
    renderStartupContextSummary(
      await compileContextDetails({
        cwd: process.cwd(),
        managedConfigPath,
        ...sessionStartProjection,
      }),
    ),
  );

  const learning = await readLearningState(projectPaths);

  console.log(
    `Automatic learning: ${config.distillation.automatic ? "enabled" : "disabled"}; last attempt ${learning.status}.`,
  );

  const skills = await readMaintenanceState(projectPaths);
  const proposals = await listSkillProposals(projectPaths);

  console.log(
    `Skill maintenance: ${config.sources["skill-library"] ? "enabled" : "disabled"}; ${skills.roots.filter((root) => root.enabled).length} root(s), ${proposals.filter((proposal) => proposal.status === "pending").length} pending proposal(s).`,
  );

  const environment = await environmentStatus(projectPaths);

  if (environment) {
    console.log(
      `Skill environment: ${environment.phase}; ${environment.skills} skills, ${environment.pending} pending learning(s), ${environment.unresolvedScopes} learning(s) in unregistered scopes.`,
    );
  } else {
    const profileRepair = await createProfileRepairPlan(projectPaths);

    console.log(
      `Profile repair: ${profileRepair.repairs.length} ready, ${profileRepair.blocked.length} blocked, ${profileRepair.isolatedDirectories} isolated.`,
    );
  }

  const dbFile = Bun.file(options.databasePath ?? projectPaths.indexDatabase);

  if (await dbFile.exists()) {
    const index = await openEventIndex(
      options.databasePath ?? projectPaths.indexDatabase,
    );

    try {
      const events = index.listEvents();
      const health = computeSourceHealth(events);

      console.log("Marker health:");

      for (const line of renderMarkerHealth({ health })) {
        console.log(`  ${line}`);
      }
    } finally {
      index.close();
    }
  }
}
