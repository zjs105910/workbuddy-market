import path from "node:path";
import {
  buildCatalog,
  buildConstellation,
  buildIdentity,
  customDocument,
  sharedRequirements,
} from "@shadowclone/builds";
import { readEffectiveConfig, canonicalPath } from "@shadowclone/core";
import {
  type BuildContext,
  type BuildScope,
  readEnvironment,
  readHarnessManifest,
} from "@shadowclone/environment";
import { loadSeedLibrary } from "@shadowclone/skills";
import { buildViewSchema, type BuildView } from "./protocol";

export async function buildView(
  options: BuildContext & {
    readonly scope: BuildScope;
    readonly revisionId: string | null;
  },
): Promise<BuildView> {
  const state = await readEnvironment(options.paths);
  const id = buildIdentity(options);
  const current = state?.builds.find((build) => build.id === id);
  const global = state?.builds.find((build) => build.scope === "global");
  const catalog = [...(await buildCatalog(options))];

  const applicable =
    state?.builds.filter(
      (build) =>
        build.scope === "global" ||
        build.directory === canonicalPath(options.cwd),
    ) ?? [];

  for (const build of applicable) {
    for (const custom of build.custom) {
      const customId = `custom:${custom.name}`;

      if (!catalog.some((item) => item.id === customId)) {
        catalog.push({
          id: customId,
          name: custom.name,
          title: custom.name.replaceAll("-", " "),
          description: custom.description,
          text: customDocument(custom),
          kind: "skill",
          category: null,
          section: null,
          axis: null,
          alwaysOn: false,
          owner: "managed",
        });
      }
    }
  }

  const { config } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath: options.paths.managedConfigFile,
  });
  const manifest =
    options.scope === "global" ? null : await readHarnessManifest(options.cwd);
  const shared = applicable.find((build) => build.scope === "shared");

  const requirements = [
    ...(manifest?.gate ? [`Required check: ${manifest.gate.command}`] : []),
    ...(manifest?.conventions.map((convention) =>
      convention.kind === "file-length"
        ? `Checked by shadowclone check: at most ${convention.maximumLines} lines per file`
        : `Checked by shadowclone check: ${convention.kind}`,
    ) ?? []),
    ...(options.scope === "private" && shared
      ? catalog
          .filter((item) => shared.choices[item.id] && !item.alwaysOn)
          .map((item) => `Shared requirement: ${item.title}`)
      : []),
  ];

  const legacy =
    state === null &&
    (await Bun.file(
      path.join(options.paths.profileDirectory, ".generated"),
    ).exists());

  return buildViewSchema.parse({
    scope: options.scope,
    input: {
      scope: options.scope,
      choices: current?.choices ?? {},
      edits: current?.edits ?? {},
      custom: current?.custom ?? [],
    },
    inherited: options.scope === "private" ? (global?.choices ?? {}) : {},
    items: catalog.map(({ source, ...item }) => item),
    constellation: buildConstellation({
      items: catalog,
      packagedIds: new Set((await loadSeedLibrary()).guidance.map((entry) => entry.id)),
    }),
    locked: {
      ...Object.fromEntries(
        catalog.filter((item) => item.alwaysOn).map((item) => [item.id, true]),
      ),
      ...(state && options.scope === "private"
        ? sharedRequirements({
            state,
            directory: canonicalPath(options.cwd),
            catalog,
          })
        : {}),
    },
    requirements,
    libraryEnabled: config.sources["skill-library"],
    migrationRequired: state?.phase === "preparing" || legacy,
    revisionId: options.revisionId,
  });
}
