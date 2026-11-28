import { readEffectiveConfig, type ShadowcloneConfig } from "@shadowclone/core";
import type { IndexedEvent, CorrectionSignal } from "@shadowclone/sessions";
import { textRefKey } from "@shadowclone/sessions";
import type { ProjectPaths } from "@shadowclone/core";

const agentContextKinds = new Set<IndexedEvent["kind"]>([
  "assistant-text",
  "plan-presented",
  "question-asked",
]);

const eligibleKinds = new Set<IndexedEvent["kind"]>([
  "user-prompt",
  "plan-resolved",
  "question-answered",
  "permission-denied",
  "interruption",
]);

export function authorizedLearningEvents(options: {
  readonly events: readonly IndexedEvent[];
  readonly config: ShadowcloneConfig;
}): readonly IndexedEvent[] {
  return options.events.filter((event) => options.config.sources[event.source]);
}

export function currentEvidenceAuthorization(options: {
  readonly paths: ProjectPaths;
  readonly configPath?: string;
  readonly events: readonly IndexedEvent[];
  readonly managedConfigPath?: string | null;
}): (ref: CorrectionSignal["textRefs"][number]) => Promise<boolean> {
  const sources = new Map(options.events.flatMap((event) =>
    event.textRef === null ? [] : [[textRefKey(event.textRef), event.source] as const]
  ));

  return async (ref) => {
    const source = sources.get(textRefKey(ref));

    if (!source) {
      return false;
    }

    const { config } = await readEffectiveConfig({
      configPath: options.configPath ?? options.paths.configFile,
      managedConfigPath: options.managedConfigPath === undefined
        ? options.paths.managedConfigFile
        : options.managedConfigPath,
    });

    return config.sources[source];
  };
}

export function isEligibleForDistillation(event: IndexedEvent): boolean {
  return eligibleKinds.has(event.kind) && event.textRef !== null;
}

export function allowlistedSignals(options: {
  readonly signals: readonly CorrectionSignal[];
  readonly events: readonly IndexedEvent[];
}): readonly CorrectionSignal[] {
  const independentlyEligibleReferences = new Set(
    options.events.flatMap((event) =>
      isEligibleForDistillation(event) && event.textRef
        ? [textRefKey(event.textRef)]
        : [],
    ),
  );

  const agentContextReferences = new Set(
    options.events.flatMap((event) =>
      agentContextKinds.has(event.kind) && event.textRef
        ? [textRefKey(event.textRef)]
        : [],
    ),
  );

  return options.signals.map((signal) => ({
    ...signal,
    contextRefs: (signal.contextRefs ?? []).filter((ref) =>
      agentContextReferences.has(textRefKey(ref)),
    ),
    textRefs: signal.textRefs.filter((ref) =>
      independentlyEligibleReferences.has(textRefKey(ref)),
    ),
  }));
}
