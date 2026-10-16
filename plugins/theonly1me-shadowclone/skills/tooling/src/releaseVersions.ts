import path from "node:path";
import { z } from "zod";

const productFileName = "product.json";

const configSchema = z.object({
  packages: z.record(
    z.string(),
    z.object({
      "extra-files": z.array(
        z.object({
          type: z.literal("json"),
          path: z.string(),
          jsonpath: z.literal("$.version"),
        }),
      ),
    }),
  ),
});

const manifestSchema = z.object({
  name: z.string().optional(),
  version: z.string(),
});

const publishedManifestFile = "packages/cli/package.json";

const publishedManifestSchema = z.object({ name: z.string() });

export type VersionSource = {
  readonly file: string;
  readonly name: string | null;
  readonly version: string;
};

export type ReleaseVersions = {
  readonly packageManifest: VersionSource;
  readonly publishedName: string;
  readonly product: VersionSource | null;
  readonly bumped: readonly VersionSource[];
};

async function readSource(options: {
  rootDirectory: string;
  file: string;
}): Promise<VersionSource> {
  const manifest = manifestSchema.parse(
    await Bun.file(path.join(options.rootDirectory, options.file)).json(),
  );

  return {
    file: options.file,
    name: manifest.name ?? null,
    version: manifest.version,
  };
}

export async function readReleaseVersions(options: {
  rootDirectory: string;
}): Promise<ReleaseVersions> {
  const config = configSchema.parse(
    await Bun.file(
      path.join(options.rootDirectory, ".github/release-please-config.json"),
    ).json(),
  );
  const files = Object.values(config.packages).flatMap((entry) =>
    entry["extra-files"].map((extra) => extra.path),
  );
  const sources = await Promise.all(
    files.map((file) =>
      readSource({ rootDirectory: options.rootDirectory, file }),
    ),
  );

  const published = publishedManifestSchema.parse(
    await Bun.file(path.join(options.rootDirectory, publishedManifestFile)).json(),
  );

  return {
    packageManifest: await readSource({
      rootDirectory: options.rootDirectory,
      file: "package.json",
    }),
    publishedName: published.name,
    product:
      sources.find(
        (source) => path.basename(source.file) === productFileName,
      ) ?? null,
    bumped: sources,
  };
}

export function findVersionMismatches(
  versions: ReleaseVersions,
): readonly string[] {
  const { product, packageManifest } = versions;

  if (product === null) {
    return [`${productFileName} is not listed in the Release Please extra-files`];
  }

  const mismatches = versions.bumped
    .filter((source) => source.version !== packageManifest.version)
    .map(
      (source) =>
        `${source.file} has version ${source.version}, but ${packageManifest.file} has ${packageManifest.version}`,
    );

  return product.name === versions.publishedName
    ? mismatches
    : [
        ...mismatches,
        `${product.file} has name ${product.name}, but ${publishedManifestFile} has ${versions.publishedName}`,
      ];
}
