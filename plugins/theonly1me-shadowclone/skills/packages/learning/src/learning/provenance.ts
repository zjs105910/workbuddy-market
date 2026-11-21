import type { SourceId } from "@shadowclone/core";
import type { IndexedEvent, CorrectionSignal } from "@shadowclone/sessions";
import { textRefKey } from "@shadowclone/sessions";
import { parseProfileEvidenceId, type ProfileRule } from "@shadowclone/profile";

export type LearningProvenance = {
  readonly sources: readonly SourceId[];
  readonly complete: boolean;
};

export function learningRuleProvenance(options: {
  readonly rule: ProfileRule;
  readonly events: readonly IndexedEvent[];
  readonly signals: readonly CorrectionSignal[];
}): LearningProvenance {
  const sources = new Set<SourceId>();
  let complete = options.rule.evidence.for.length > 0;
  const eventSources = new Map(options.events.flatMap((event) =>
    event.textRef ? [[textRefKey(event.textRef), event.source] as const] : [],
  ));

  for (const identifier of options.rule.evidence.for) {
    const moment = parseProfileEvidenceId(identifier);

    if (moment === null) {
      complete = false;
      continue;
    }

    const signal = options.signals.find((entry) =>
      entry.sessionId === moment.sessionId && entry.timestamp === moment.timestamp &&
      entry.origin.id === moment.originId,
    );
    const supportingSources = signal
      ? signal.textRefs.flatMap((ref) => {
          const source = eventSources.get(textRefKey(ref));
          return source ? [source] : [];
        })
      : options.events.filter((event) => {
          const source = event.source === "claude-prompts" ? "claude-code" : event.source;
          return `${source}:${event.sessionId}` === moment.sessionId;
        }).map((event) => event.source);

    if (supportingSources.length === 0 ||
      (signal && supportingSources.length !== signal.textRefs.length)) {
      complete = false;
    }

    for (const source of supportingSources) {
      sources.add(source);
    }
  }

  return { sources: [...sources].sort(), complete };
}
