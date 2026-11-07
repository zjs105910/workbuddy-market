import {
  fingerprint,
  readLocalText,
  replaceLocalText,
  createProjectPaths,
} from "@shadowclone/core";
import { emptyHookConfig, hasOwnedHooks, updateHookConfig } from "./hookConfig";
import {
  guidanceMarkers,
  markedSection,
  renderContextSkill,
  renderInstructionPointer,
  updateManagedSection,
} from "./markdown";
import { integrationFilePath, integrationTargets, retiredIntegrationTargets } from "./targets";
import type { Integration, IntegrationFile } from "./types";
import { renderPiExtension } from "./piExtension";
import { readIntegrations } from "./state";
import { importsPeerInstructions } from "./sharedInstructions";

export type IntegrationFileChange = {
  readonly filePath: string;
  readonly previous: string | null;
  readonly next: string | null;
  readonly record: IntegrationFile;
  readonly retired?: boolean;
};

export function savedRecords(changes: readonly IntegrationFileChange[]): IntegrationFile[] {
  return changes.flatMap((change) => (change.retired ? [] : [change.record]));
}

export async function prepareIntegrationFiles(options: {
  readonly integration: Integration;
  readonly profile: string;
  readonly remove?: boolean;
  readonly environment?: boolean;
  readonly peers?: readonly Integration[];
}): Promise<readonly IntegrationFileChange[]> {
  const changes: IntegrationFileChange[] = [];
  const integrations = await readIntegrations(createProjectPaths({ homeDirectory: options.integration.userDirectory, platform: process.platform }));

  for (const target of integrationTargets(options.integration)) {
    const filePath = integrationFilePath({
      integration: options.integration,
      file: target,
    });
    const previous = await readLocalText(filePath);
    const shared = integrations.flatMap((integration) => integration.id === options.integration.id ? [] :
      integration.files.filter((file) => integrationFilePath({ integration, file }) === filePath));
    const recorded = options.integration.files.find(
      (file) => file.relativePath === target.relativePath,
    ) ?? shared[0];

    if (options.remove && shared.length > 0) continue;

    if (options.remove && (!recorded || previous === null)) {
      continue;
    }

    let next: string | null;
    let digest: string;

    if (target.kind === "hooks") {
      if (
        recorded &&
        previous !== null &&
        !hasOwnedHooks({ text: previous, integration: options.integration })
      ) {
        throw new Error("Integration hooks were edited; preserving the file");
      }

      const changed = updateHookConfig({
        previous,
        integration: options.integration,
        remove: options.remove,
      });

      next = changed.text;
      digest = changed.fingerprint;

      if (options.remove && recorded?.created && emptyHookConfig(next)) {
        next = null;
      }
    } else if (target.kind === "skill" || target.kind === "extension") {
      if (
        previous !== null &&
        (!recorded || (fingerprint(previous) !== recorded.fingerprint &&
          !shared.some(file => file.kind === target.kind && file.fingerprint === fingerprint(previous))))
      ) {
        throw new Error(
          "Integration skill or extension was edited or already exists; preserving it",
        );
      }

      next = options.remove
        ? null
        : target.kind === "extension" ? renderPiExtension(options.integration)
        : `${renderContextSkill(options.environment)}\n`;
      digest = fingerprint(next ?? "");
    } else {
      const prefix =
        previous === null && options.integration.agent === "cursor"
          ? "---\ndescription: Personal engineering preferences from Shadowclone\nalwaysApply: true\n---\n"
          : previous;
      const importsPeer = importsPeerInstructions({
        integration: options.integration,
        filePath,
        text: previous,
        peers: options.peers ?? integrations,
      });
      const changed = updateManagedSection({
        previous: prefix,
        body: options.remove || importsPeer
          ? null
          : options.environment
            ? options.profile
            : renderInstructionPointer(),
        expected: recorded?.fingerprint,
      });

      next = changed.text;
      digest = changed.fingerprint;

      const empty =
        next.trim() === "" ||
        next ===
          "---\ndescription: Personal engineering preferences from Shadowclone\nalwaysApply: true\n---\n";

      if (options.remove && recorded?.created && empty) {
        next = null;
      }
    }

    changes.push({
      filePath,
      previous,
      next,
      record: {
        ...target,
        fingerprint: digest,
        created: recorded?.created ?? previous === null,
      },
    });
  }

  for (const target of retiredIntegrationTargets(options.integration)) {
    const recorded = options.integration.files.find(
      (file) => file.relativePath === target.relativePath && file.kind === target.kind,
    );
    const filePath = integrationFilePath({ integration: options.integration, file: target });
    const previous = recorded ? await readLocalText(filePath) : null;

    if (
      !recorded ||
      previous === null ||
      markedSection({ text: previous, markers: guidanceMarkers }) === null
    ) {
      continue;
    }

    const changed = updateManagedSection({ previous, body: null, expected: recorded.fingerprint });

    changes.push({
      filePath,
      previous,
      next: recorded.created && changed.text.trim() === "" ? null : changed.text,
      record: { ...target, fingerprint: changed.fingerprint, created: recorded.created },
      retired: true,
    });
  }

  return changes;
}

export async function applyIntegrationFiles(
  changes: readonly IntegrationFileChange[],
): Promise<void> {
  const completed: IntegrationFileChange[] = [];

  try {
    for (const change of changes) {
      await replaceLocalText(change);
      completed.push(change);
    }
  } catch (error) {
    for (const change of completed.reverse()) {
      await replaceLocalText({
        filePath: change.filePath,
        previous: change.next,
        next: change.previous,
      });
    }

    throw error;
  }
}
