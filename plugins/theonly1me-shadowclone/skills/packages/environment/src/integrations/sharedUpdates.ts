import type { FileUpdate } from "@shadowclone/changes";

export function sharedIntegrationUpdates(updates: readonly FileUpdate[]): readonly FileUpdate[] {
  const shared = new Map<string, FileUpdate>();
  for (const update of updates) {
    const previous = shared.get(update.filePath);
    if (previous && (previous.previous !== update.previous || previous.next !== update.next)) {
      throw new Error("Shared integration files have conflicting managed content");
    }
    shared.set(update.filePath, update);
  }
  return [...shared.values()];
}
