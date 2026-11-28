import type { GeneratedProfileStateEntry, ProfileRejection } from "./state";

export function profileRejectionFromState(
  entry: GeneratedProfileStateEntry,
): ProfileRejection {
  return {
    relativePath: entry.relativePath,
    key: entry.key,
    title: entry.title,
    body: entry.body,
    source: entry.source,
    importReference: entry.importReference,
    reason: "user-rejected",
  };
}
