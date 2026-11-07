import path from "node:path";
import { z } from "zod";
import { packageLayout, packageNames, type PackageLayout, type PackageName } from "./packages";
import { parseWorkspaceSpecifier, workspaceNameOf } from "./specifiers";

export type WorkspaceKey = PackageName | "root" | "evals" | "tooling";

export type WorkspaceManifest = {
  readonly file: string;
  readonly name: string | null;
  readonly version: string | null;
  readonly isPrivate: boolean;
  readonly exportedSubpaths: readonly string[];
  readonly workspaceDependencies: readonly string[];
};

export type ManifestIndex = ReadonlyMap<WorkspaceKey, WorkspaceManifest>;

export type ManifestViolation = {
  readonly file: string;
  readonly line: number;
  readonly message: string;
};

const manifestSchema = z.object({
  name: z.string().optional(),
  version: z.string().optional(),
  private: z.boolean().optional(),
  exports: z.record(z.string(), z.unknown()).optional(),
  dependencies: z.record(z.string(), z.string()).optional(),
  devDependencies: z.record(z.string(), z.string()).optional(),
});

function manifestFileOf(key: WorkspaceKey): string {
  if (key === "root") {
    return "package.json";
  }

  return key === "evals" || key === "tooling"
    ? `${key}/package.json`
    : `packages/${key}/package.json`;
}

export async function readManifests(rootDirectory: string): Promise<ManifestIndex> {
  const keys: readonly WorkspaceKey[] = ["root", "evals", "tooling", ...packageNames];
  const manifests = new Map<WorkspaceKey, WorkspaceManifest>();

  for (const key of keys) {
    const file = manifestFileOf(key);
    const source = Bun.file(path.join(rootDirectory, file));

    if (!(await source.exists())) {
      continue;
    }

    const parsed = manifestSchema.parse(await source.json());
    const dependencies = { ...parsed.dependencies, ...parsed.devDependencies };

    manifests.set(key, {
      file,
      name: parsed.name ?? null,
      version: parsed.version ?? null,
      isPrivate: parsed.private === true,
      exportedSubpaths: Object.keys(parsed.exports ?? {}),
      workspaceDependencies: Object.keys(dependencies).filter(
        (name) => parseWorkspaceSpecifier(name) !== null,
      ),
    });
  }

  return manifests;
}

function packageManifestMessages(options: {
  readonly name: PackageName;
  readonly manifest: WorkspaceManifest;
  readonly layout: PackageLayout;
}): readonly string[] {
  const { name, manifest, layout } = options;
  const messages: string[] = [];

  if (manifest.name !== workspaceNameOf(name)) {
    messages.push(`the package must be named ${workspaceNameOf(name)}`);
  }

  if (!manifest.isPrivate) {
    messages.push("a workspace package must be private");
  }

  if (manifest.version !== null) {
    messages.push("a workspace package has no version");
  }

  for (const dependency of manifest.workspaceDependencies) {
    const declared = parseWorkspaceSpecifier(dependency)?.packageName;
    const allowed = layout.allowedDependencies[name].map((allowedName) =>
      workspaceNameOf(allowedName),
    );

    if (!allowed.includes(dependency)) {
      messages.push(`${declared} is not a dependency that ${name} may declare`);
    }
  }

  return messages;
}

export function manifestViolations(options: {
  readonly manifests: ManifestIndex;
  readonly layout?: PackageLayout;
}): readonly ManifestViolation[] {
  const layout = options.layout ?? packageLayout;
  const violations: ManifestViolation[] = [];

  for (const [key, manifest] of options.manifests) {
    const messages =
      key === "root" || key === "evals" || key === "tooling"
        ? manifest.workspaceDependencies
            .filter((dependency) => {
              const declared = parseWorkspaceSpecifier(dependency)?.packageName;
              return !packageNames.some((name) => name === declared);
            })
            .map((dependency) => `${dependency} is not a workspace package`)
        : packageManifestMessages({ name: key, manifest, layout });

    for (const message of messages) {
      violations.push({ file: manifest.file, line: 1, message });
    }
  }

  return violations;
}
