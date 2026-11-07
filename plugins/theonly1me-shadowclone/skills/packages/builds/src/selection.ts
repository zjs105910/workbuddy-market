import path from "node:path";
import { fingerprint, canonicalPath } from "@shadowclone/core";
import { validateSharedRequirements } from "./requirements";
import type {
  BuildContext,
  BuildDefinition,
  BuildInput,
  BuildScope,
  EnvironmentState,
} from "@shadowclone/environment";
import type { BuildItem } from "./types";

export function buildIdentity(
  options: BuildContext & { readonly scope: BuildScope },
): string {
  return options.scope === "global"
    ? "global"
    : `${options.scope}-${fingerprint(canonicalPath(options.cwd)).slice(0, 24)}`;
}

export function buildDefinition(
  options: BuildContext & { readonly input: BuildInput },
): BuildDefinition {
  return {
    ...options.input,
    id: buildIdentity({ ...options, scope: options.input.scope }),
    directory:
      options.input.scope === "global"
        ? path.dirname(options.paths.shadowcloneDirectory)
        : canonicalPath(options.cwd),
  };
}

export function effectiveChoices(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
}): Readonly<Record<string, boolean>> {
  const global = options.state.builds.find((build) => build.scope === "global");

  return {
    ...(options.build.scope === "private" ? global?.choices : {}),
    ...options.build.choices,
  };
}

export function selectedItems(options: {
  readonly state: EnvironmentState;
  readonly build: BuildDefinition;
  readonly catalog: readonly BuildItem[];
}): readonly BuildItem[] {
  const locked = validateSharedRequirements(options);
  const choices = { ...effectiveChoices(options), ...locked };
  const selected = options.catalog.filter(
    (item) => (item.alwaysOn || choices[item.id]) && locked[item.id] !== true,
  );

  for (const [id, chosen] of Object.entries(options.build.choices)) {
    if (
      chosen &&
      !options.catalog.some((item) => item.id === id) &&
      !options.build.custom.some((skill) => id === `custom:${skill.name}`)
    ) {
      throw new Error(
        "The selected library changed; reload the build before applying",
      );
    }
  }

  for (const id of Object.keys(options.build.edits)) {
    const item = selected.find((candidate) => candidate.id === id);
    const custom = options.build.custom.some(
      (skill) => id === `custom:${skill.name}` && choices[id] !== false,
    );

    if (custom) {
      continue;
    }

    if (!item || item.owner === "provider") {
      throw new Error(
        "Only selected user-owned skills can be edited; create a companion for provider skills",
      );
    }
  }

  const axes = selected.flatMap((item) => (item.axis ? [item.axis] : []));

  if (new Set(axes).size !== axes.length) {
    throw new Error("Choose one option for each workflow preference");
  }

  return selected;
}

export function customDocument(skill: {
  readonly name: string;
  readonly description: string;
  readonly body: string;
}): string {
  return `---\nname: ${skill.name}\ndescription: ${JSON.stringify(skill.description)}\n---\n\n${skill.body.trim()}\n`;
}
