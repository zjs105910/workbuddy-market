import os from "node:os";
import path from "node:path";

const workspaceRoot = path.resolve(import.meta.dir, "../../..");

const runtimeModulePaths: Bun.BunPlugin = {
  name: "runtime-module-paths",
  setup(build) {
    build.onLoad(
      { filter: /[/\\]typescript[/\\]lib[/\\]typescript\.js$/ },
      async ({ path: modulePath }) => ({
        contents: `const __dirname = import.meta.dir; const __filename = import.meta.path;\n${await Bun.file(modulePath).text()}`,
        loader: "js",
      }),
    );
  },
};

export async function buildRuntimeArtifacts(
  entryPoint: string,
): Promise<readonly Bun.BuildArtifact[]> {
  const result = await Bun.build({
    entrypoints: [entryPoint],
    target: "bun",
    minify: true,
    plugins: [runtimeModulePaths],
    naming: {
      asset: "web/[name]-[hash].[ext]",
      chunk: "web/[name]-[hash].[ext]",
    },
  });

  if (!result.success || result.outputs.length === 0) {
    throw new Error("Runtime bundle failed to build");
  }

  const privateRoots = [
    process.cwd(),
    workspaceRoot,
    os.homedir(),
    path.dirname(path.resolve(entryPoint)),
  ];

  for (const artifact of result.outputs) {
    const text = await artifact.text();

    if (privateRoots.some((root) => text.includes(root))) {
      throw new Error("Runtime bundle contains a build-machine path");
    }
  }

  return result.outputs;
}

export async function buildRuntimeBundle(
  entryPoint: string,
): Promise<Bun.BuildArtifact> {
  const [bundle] = await buildRuntimeArtifacts(entryPoint);

  if (!bundle) {
    throw new Error("Runtime bundle failed to build");
  }

  return bundle;
}

export async function writeRuntimeArtifacts(options: {
  readonly artifacts: readonly Bun.BuildArtifact[];
  readonly distDirectory: string;
}): Promise<string> {
  const bundleFile = path.join(options.distDirectory, "shadowclone.js");

  for (const [index, artifact] of options.artifacts.entries()) {
    const relativePath = path.relative(process.cwd(), artifact.path);

    if (relativePath.startsWith("..") || path.isAbsolute(relativePath)) {
      throw new Error("Build output escapes its destination");
    }

    const destination =
      index === 0 ? bundleFile : path.join(options.distDirectory, relativePath);

    await Bun.write(destination, artifact);
  }

  return bundleFile;
}
