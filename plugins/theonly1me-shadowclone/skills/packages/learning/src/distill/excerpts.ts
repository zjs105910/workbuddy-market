import { extractPromptText } from "./promptText";
import { stripManagedGuidance } from "@shadowclone/environment";
import {
  textRefKey,
  resolveRedacted,
  hasDurableSteeringCue,
  type CorrectionSignal,
} from "@shadowclone/sessions";

export const internalLearningMarker = "SHADOWCLONE_INTERNAL_LEARNING";

export async function materializeEvidence(options: {
  readonly signals: readonly CorrectionSignal[];
  readonly sourceRoots?: readonly string[];
  readonly requireSteeringCue?: boolean;
  readonly authorizeRef?: (ref: CorrectionSignal["textRefs"][number]) => Promise<boolean>;
}): Promise<{
  readonly signals: readonly CorrectionSignal[];
  readonly excerpts: ReadonlyMap<string, string>;
}> {
  const excerpts = new Map<string, string>();
  const accepted: CorrectionSignal[] = [];

  for (const signal of options.signals) {
    const textRefs = [];

    for (const ref of signal.textRefs) {
      if (options.authorizeRef && !(await options.authorizeRef(ref))) {
        continue;
      }

      const redacted = await resolveRedacted({
        ref,
        roots: options.sourceRoots,
      });
      const text =
        signal.kind === "user-steering"
          ? (extractPromptText(redacted) ?? "")
          : redacted;

      if (
        text.includes(internalLearningMarker) ||
        text.trimStart().startsWith("# Shadowclone profile")
      ) {
        continue;
      }

      const authored = stripManagedGuidance(text);

      if (!authored.trim()) {
        continue;
      }

      excerpts.set(textRefKey(ref), authored);
      textRefs.push(ref);
    }

    if (textRefs.length === 0) {
      continue;
    }

    const lacksCue =
      options.requireSteeringCue === true &&
      signal.kind === "user-steering" &&
      !textRefs.some((ref) =>
        hasDurableSteeringCue(excerpts.get(textRefKey(ref)) ?? ""),
      );

    if (lacksCue) {
      for (const ref of textRefs) {
        excerpts.delete(textRefKey(ref));
      }

      continue;
    }

    for (const ref of signal.contextRefs ?? []) {
      if (options.authorizeRef && !(await options.authorizeRef(ref))) {
        continue;
      }

      const text = await resolveRedacted({ ref, roots: options.sourceRoots });

      excerpts.set(
        textRefKey(ref),
        signal.kind === "user-steering" ? (extractPromptText(text) ?? "") : text,
      );
    }

    accepted.push({ ...signal, textRefs });
  }

  return { signals: accepted, excerpts };
}
