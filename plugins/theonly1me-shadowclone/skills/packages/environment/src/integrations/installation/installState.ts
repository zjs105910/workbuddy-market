import path from "node:path";
import { readBoundedFile, ownedWrite } from "@shadowclone/core";
import { z } from "zod";

export type InstalledArtifact = "agent" | "delegation-skill";

export type Installation = {
  readonly directory: string;
  readonly artifacts: readonly InstalledArtifact[];
  readonly excludes: readonly string[];
  readonly fingerprints?: Partial<Record<InstalledArtifact, string>>;
};

export type InstallationState = {
  readonly version: 1;
  readonly installations: readonly Installation[];
};

const installationStateSchema = z.strictObject({
  version: z.literal(1),
  installations: z.array(
    z.strictObject({
      directory: z.string().min(1),
      artifacts: z.array(z.enum(["agent", "delegation-skill"])),
      excludes: z.array(z.string().min(1)),
      fingerprints: z
        .object({
          agent: z.string().optional(),
          "delegation-skill": z.string().optional(),
        })
        .optional(),
    }),
  ),
});

export const emptyInstallationState: InstallationState = {
  version: 1,
  installations: [],
};

export async function readInstallations(
  filePath: string,
): Promise<InstallationState> {
  const file = Bun.file(filePath);

  if (!(await file.exists())) {
    return emptyInstallationState;
  }

  try {
    const text = await readBoundedFile({
      filePath,
      roots: [path.dirname(filePath)],
      maximumBytes: 1024 * 1024,
    });

    if (text === null) {
      throw new Error("Installation state could not be read safely");
    }

    const parsed = installationStateSchema.safeParse(JSON.parse(text));

    return parsed.success ? parsed.data : emptyInstallationState;
  } catch {
    return emptyInstallationState;
  }
}

export async function writeInstallations(options: {
  readonly filePath: string;
  readonly state: InstallationState;
}): Promise<void> {
  await ownedWrite({
    path: options.filePath,
    content: `${JSON.stringify(options.state, null, 2)}\n`,
  });
}

export function findInstallation(options: {
  readonly state: InstallationState;
  readonly directory: string;
}): Installation | null {
  return (
    options.state.installations.find(
      (entry) => entry.directory === options.directory,
    ) ?? null
  );
}

function unionSorted<Value extends string>(
  left: readonly Value[],
  right: readonly Value[],
): readonly Value[] {
  return [...new Set([...left, ...right])].sort();
}

export function mergeInstallation(options: {
  readonly state: InstallationState;
  readonly installation: Installation;
}): InstallationState {
  const previous = findInstallation({
    state: options.state,
    directory: options.installation.directory,
  });
  const merged: Installation = {
    directory: options.installation.directory,
    fingerprints: {
      ...previous?.fingerprints,
      ...options.installation.fingerprints,
    },
    artifacts: unionSorted(
      previous?.artifacts ?? [],
      options.installation.artifacts,
    ),
    excludes: unionSorted(
      previous?.excludes ?? [],
      options.installation.excludes,
    ),
  };

  return {
    version: 1,
    installations: [
      ...options.state.installations.filter(
        (entry) => entry.directory !== merged.directory,
      ),
      merged,
    ],
  };
}

export function removeInstallation(options: {
  readonly state: InstallationState;
  readonly directory: string;
}): InstallationState {
  return {
    version: 1,
    installations: options.state.installations.filter(
      (entry) => entry.directory !== options.directory,
    ),
  };
}
