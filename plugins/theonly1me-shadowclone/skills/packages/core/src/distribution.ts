import { stat } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import product from "./product.json";

export type SeedDirectories = {
  readonly preferences: string;
  readonly skills: string;
};

const packageManifestSchema = z.object({ name: z.string() });
const workspaceManifestSchema = z.object({ workspaces: z.array(z.string()) });
const packagesWorkspace = "packages/*";

async function isDirectory(directory: string): Promise<boolean> {
  return stat(directory)
    .then((metadata) => metadata.isDirectory())
    .catch(() => false);
}

async function readManifest(rootDirectory: string): Promise<unknown> {
  const manifest = Bun.file(path.join(rootDirectory, "package.json"));

  return (await manifest.exists()) ? await manifest.json().catch(() => null) : null;
}

async function hasSeedFolders(rootDirectory: string): Promise<boolean> {
  return (
    (await isDirectory(path.join(rootDirectory, "skills"))) &&
    (await isDirectory(path.join(rootDirectory, "preferences")))
  );
}

export async function isPackageRoot(rootDirectory: string): Promise<boolean> {
  const parsed = packageManifestSchema.safeParse(await readManifest(rootDirectory));

  return (
    parsed.success &&
    parsed.data.name === product.name &&
    (await hasSeedFolders(rootDirectory))
  );
}

async function isWorkspaceRoot(rootDirectory: string): Promise<boolean> {
  const parsed = workspaceManifestSchema.safeParse(await readManifest(rootDirectory));

  return (
    parsed.success &&
    parsed.data.workspaces.includes(packagesWorkspace) &&
    (await hasSeedFolders(rootDirectory))
  );
}

async function findWorkspaceRoot(startDirectory: string): Promise<string | null> {
  let current = startDirectory;

  while (!current.split(path.sep).includes("node_modules")) {
    if (await isWorkspaceRoot(current)) {
      return current;
    }

    const parent = path.dirname(current);

    if (parent === current) {
      return null;
    }

    current = parent;
  }

  return null;
}

function seedDirectoriesOf(rootDirectory: string): SeedDirectories {
  return {
    preferences: path.join(rootDirectory, "preferences"),
    skills: path.join(rootDirectory, "skills"),
  };
}

export async function resolveSeedDirectoriesFrom(
  moduleDirectory: string,
): Promise<SeedDirectories> {
  const packageRoot = path.resolve(moduleDirectory, "..");

  if (await isPackageRoot(packageRoot)) {
    return seedDirectoriesOf(packageRoot);
  }

  const workspaceRoot = await findWorkspaceRoot(packageRoot);

  if (workspaceRoot !== null) {
    return seedDirectoriesOf(workspaceRoot);
  }

  throw new Error("The packaged seed guidance directories are missing");
}

export async function resolveSeedDirectories(): Promise<SeedDirectories> {
  return resolveSeedDirectoriesFrom(import.meta.dir);
}

export async function seedSkillsDirectory(): Promise<string> {
  return (await resolveSeedDirectories()).skills;
}
