import type { GeneratedProfileStateEntry, ProfileRejection } from "./state";

function ordered<
  T extends { readonly relativePath: string; readonly key: string },
>(entries: readonly T[]): readonly T[] {
  return entries
    .slice()
    .sort(
      (left, right) =>
        left.relativePath.localeCompare(right.relativePath) ||
        left.key.localeCompare(right.key),
    );
}

export function renderGeneratedProfileState(
  entries: readonly GeneratedProfileStateEntry[],
): string {
  const lines = ordered(entries).map((entry) =>
    JSON.stringify({ schema: 1, ...entry }),
  );

  return lines.length > 0 ? `${lines.join("\n")}\n` : "";
}

export function renderProfileRejections(
  entries: readonly ProfileRejection[],
): string {
  const lines = ordered(entries).map((entry) =>
    JSON.stringify({ schema: 1, ...entry }),
  );

  return lines.length > 0 ? `${lines.join("\n")}\n` : "";
}
