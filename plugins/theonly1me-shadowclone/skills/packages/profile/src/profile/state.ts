import { parseGeneratedLine, parseRejectionLine } from "./stateParsing";
import type { ProfileImportReference, ProfileSource } from "./types";
import type { ProfileRejectionReason } from "./rejection";

export type GeneratedProfileStateEntry = {
  readonly relativePath: string;
  readonly key: string;
  readonly title: string | null;
  readonly body: string | null;
  readonly source: ProfileSource | null;
  readonly importReference: ProfileImportReference | null;
  readonly disposition: "present" | "retired";
};

export type ProfileRejection = {
  readonly relativePath: string;
  readonly key: string;
  readonly title: string | null;
  readonly body: string | null;
  readonly source: ProfileSource | null;
  readonly importReference: ProfileImportReference | null;
  readonly reason?: ProfileRejectionReason | null;
};

export type { ProfileRejectionReason } from "./rejection";

async function stateLines(statePath: string): Promise<readonly string[]> {
  const file = Bun.file(statePath);

  if (!(await file.exists())) {
    return [];
  }

  return (await file.text())
    .split("\n")
    .filter((line) => line.trim().length > 0);
}

export function parseProfileRejectionText(
  text: string,
): readonly ProfileRejection[] {
  const entries: ProfileRejection[] = [];

  for (const line of text
    .split("\n")
    .filter((value) => value.trim().length > 0)) {
    const entry = parseRejectionLine(line);

    if (!entry) {
      throw new Error("Profile rejection state contains an invalid entry");
    }

    entries.push(entry);
  }

  return entries;
}

export async function readGeneratedProfileState(
  statePath: string,
): Promise<readonly GeneratedProfileStateEntry[]> {
  const entries: GeneratedProfileStateEntry[] = [];

  for (const line of await stateLines(statePath)) {
    const entry = parseGeneratedLine(line);

    if (!entry) {
      throw new Error("Generated profile state contains an invalid entry");
    }

    entries.push(entry);
  }

  return entries;
}

export async function readProfileRejections(
  statePath: string,
): Promise<readonly ProfileRejection[]> {
  return parseProfileRejectionText((await stateLines(statePath)).join("\n"));
}

export { profileRejectionFromState } from "./rejectionFromState";
