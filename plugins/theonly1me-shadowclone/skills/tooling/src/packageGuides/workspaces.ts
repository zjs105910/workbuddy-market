import path from "node:path";
import { z } from "zod";

export type Workspace = {
  readonly directory: string;
  readonly name: string;
  readonly workspaceDependencies: readonly string[];
  readonly externalDependencies: readonly string[];
  readonly exportSubpaths: readonly string[];
};

const rootSchema = z.object({ workspaces: z.array(z.string()) });
const manifestSchema = z.object({
  name: z.string(),
  dependencies: z.record(z.string(), z.string()).optional(),
  exports: z.union([z.string(), z.record(z.string(), z.unknown())]).optional(),
});

const workspaceRangePrefix = "workspace:";

function subpathsOf(exported: z.infer<typeof manifestSchema>["exports"]): readonly string[] {
  if (exported === undefined) {
    return [];
  }

  return typeof exported === "string" ? ["."] : Object.keys(exported);
}

export async function readWorkspaces(options: {
  readonly rootDirectory: string;
}): Promise<readonly Workspace[]> {
  const root = rootSchema.parse(
    await Bun.file(path.join(options.rootDirectory, "package.json")).json(),
  );
  const directories: string[] = [];

  for (const pattern of root.workspaces) {
    for await (const manifest of new Bun.Glob(`${pattern}/package.json`).scan({
      cwd: options.rootDirectory,
      onlyFiles: true,
    })) {
      directories.push(path.posix.dirname(manifest));
    }
  }

  const workspaces: Workspace[] = [];

  for (const directory of directories.sort()) {
    const manifest = manifestSchema.parse(
      await Bun.file(path.join(options.rootDirectory, directory, "package.json")).json(),
    );
    const dependencies = Object.entries(manifest.dependencies ?? {});

    workspaces.push({
      directory,
      name: manifest.name,
      workspaceDependencies: dependencies
        .filter(([, range]) => range.startsWith(workspaceRangePrefix))
        .map(([name]) => name),
      externalDependencies: dependencies
        .filter(([, range]) => !range.startsWith(workspaceRangePrefix))
        .map(([name]) => name),
      exportSubpaths: subpathsOf(manifest.exports),
    });
  }

  return workspaces;
}
