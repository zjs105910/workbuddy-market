import { cp, mkdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import product from "@shadowclone/core/product.json";
import { publishedManifest, type PublishedManifest } from "./publishedManifest";

const binEntry = "bin";
const distEntry = "dist";

async function exists(location: string): Promise<boolean> {
  return stat(location).then(
    () => true,
    () => false,
  );
}

export async function stageCliPackage(options: {
  readonly packageDirectory: string;
  readonly distDirectory: string;
  readonly workspaceRoot: string;
  readonly outputDirectory: string;
}): Promise<PublishedManifest> {
  const manifest = publishedManifest({
    cliManifest: await Bun.file(path.join(options.packageDirectory, "package.json")).json(),
    product,
  });

  const sources = manifest.files.map((entry) => ({
    entry,
    source:
      entry === binEntry
        ? path.join(options.packageDirectory, binEntry)
        : entry === distEntry
          ? options.distDirectory
          : path.join(options.workspaceRoot, entry),
  }));

  const missing: string[] = [];

  for (const { entry, source } of sources) {
    if (!(await exists(source))) {
      missing.push(`${entry} (${source})`);
    }
  }

  if (missing.length > 0) {
    throw new Error(
      `The cli package cannot be staged because these inputs are missing: ${missing.join(", ")}. Run the build first.`,
    );
  }

  await rm(options.outputDirectory, { recursive: true, force: true });
  await mkdir(options.outputDirectory, { recursive: true });

  for (const { entry, source } of sources) {
    await cp(source, path.join(options.outputDirectory, entry), { recursive: true });
  }

  await Bun.write(
    path.join(options.outputDirectory, "package.json"),
    `${JSON.stringify(manifest, null, 2)}\n`,
  );

  return manifest;
}

if (import.meta.main) {
  const packageDirectory = path.resolve(import.meta.dir, "..");
  const outputDirectory = path.join(packageDirectory, "out/package");
  const manifest = await stageCliPackage({
    packageDirectory,
    distDirectory: path.join(packageDirectory, distEntry),
    workspaceRoot: path.resolve(packageDirectory, "../.."),
    outputDirectory,
  });

  console.log(
    `${manifest.name}@${manifest.version} staged in ${path.relative(process.cwd(), outputDirectory)}`,
  );
}
