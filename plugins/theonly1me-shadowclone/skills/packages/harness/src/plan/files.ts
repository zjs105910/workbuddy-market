import { lstat } from "node:fs/promises";
import path from "node:path";
import { harnessMarkers, updateMarkedSection } from "@shadowclone/environment";
import { fingerprint, readLocalText } from "@shadowclone/core";
import {
  claudeSettingsPath,
  mergeClaudeStopHook,
} from "../render/claudeSettings";

export type PlannedFileStatus =
  | "create"
  | "update"
  | "unchanged"
  | "preserved"
  | "skipped";

export type PlannedFile = {
  readonly relativePath: string;
  readonly status: PlannedFileStatus;
  readonly previous: string | null;
  readonly next: string | null;
  readonly fingerprint: string | null;
  readonly reason: string;
};

async function isSymbolicLink(filePath: string): Promise<boolean> {
  return (await lstat(filePath).catch(() => null))?.isSymbolicLink() === true;
}

export async function planManagedFile(options: {
  readonly root: string;
  readonly relativePath: string;
  readonly initial: string;
  readonly body: string;
  readonly expected: string | undefined;
  readonly reason: string;
}): Promise<PlannedFile> {
  const filePath = path.join(options.root, options.relativePath);
  const base = { relativePath: options.relativePath, reason: options.reason };

  if (await isSymbolicLink(filePath)) {
    return {
      ...base,
      status: "skipped",
      previous: null,
      next: null,
      fingerprint: null,
      reason: "is a symbolic link, so it was left alone",
    };
  }

  const previous = await readLocalText(filePath);

  try {
    const updated = updateMarkedSection({
      previous: previous ?? options.initial,
      body: options.body,
      expected: previous === null ? undefined : options.expected,
      markers: harnessMarkers,
    });
    const status =
      previous === null
        ? "create"
        : updated.text === previous
          ? "unchanged"
          : "update";

    return {
      ...base,
      status,
      previous,
      next: updated.text,
      fingerprint: updated.fingerprint,
    };
  } catch (error) {
    const reason =
      error instanceof Error ? error.message : "could not be updated";

    return {
      ...base,
      status: "preserved",
      previous,
      next: null,
      fingerprint: options.expected ?? null,
      reason,
    };
  }
}

export async function planOwnedFile(options: {
  readonly root: string;
  readonly relativePath: string;
  readonly next: string;
  readonly recorded: string | undefined;
  readonly reason: string;
}): Promise<PlannedFile> {
  const filePath = path.join(options.root, options.relativePath);
  const base = { relativePath: options.relativePath, reason: options.reason };

  if (await isSymbolicLink(filePath)) {
    return {
      ...base,
      status: "skipped",
      previous: null,
      next: null,
      fingerprint: null,
      reason: "is a symbolic link, so it was left alone",
    };
  }

  const previous = await readLocalText(filePath);
  const created = {
    ...base,
    previous,
    next: options.next,
    fingerprint: fingerprint(options.next),
  };

  if (previous === null) {
    return { ...created, status: "create" };
  }

  if (previous === options.next) {
    return { ...created, status: "unchanged" };
  }

  if (
    options.recorded !== undefined &&
    fingerprint(previous) === options.recorded
  ) {
    return { ...created, status: "update" };
  }

  const reason =
    options.recorded === undefined
      ? "already exists and is not managed by Shadowclone"
      : "was edited after Shadowclone wrote it";

  return {
    ...base,
    status: "preserved",
    previous,
    next: null,
    fingerprint: options.recorded ?? null,
    reason,
  };
}

export async function planClaudeStopHook(root: string): Promise<PlannedFile> {
  const base = {
    relativePath: claudeSettingsPath,
    fingerprint: null,
    reason: "your Claude Stop hook that runs shadowclone check",
  };

  if (await isSymbolicLink(path.join(root, claudeSettingsPath))) {
    return {
      ...base,
      status: "skipped",
      previous: null,
      next: null,
      reason: "is a symbolic link, so it was left alone",
    };
  }

  const previous = await readLocalText(path.join(root, claudeSettingsPath));

  try {
    const next = mergeClaudeStopHook(previous);

    return {
      ...base,
      status:
        previous === null
          ? "create"
          : next === previous
            ? "unchanged"
            : "update",
      previous,
      next,
    };
  } catch (error) {
    return {
      ...base,
      status: "preserved",
      previous,
      next: null,
      reason: error instanceof Error ? error.message : "could not be updated",
    };
  }
}

export function importsAgentsFile(text: string | null): boolean {
  return (
    text?.split("\n").some((line) => line.trim() === "@AGENTS.md") ?? false
  );
}
