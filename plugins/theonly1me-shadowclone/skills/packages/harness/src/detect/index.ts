import type { KnownTool } from "@shadowclone/profile";
import type { RepositoryFacts } from "../types";
import { readManifest, readManifestDirectory, readRootEntries } from "./files";
import { makeTargets } from "./make";
import { detectNode } from "./node";
import { detectPython, hasPythonProject } from "./python";

const entryTools: readonly (readonly [string, KnownTool])[] = [
  ["Cargo.toml", "rust"],
  ["go.mod", "go"],
  ["Dockerfile", "docker"],
  ["Makefile", "make"],
];

export async function detectRepository(root: string): Promise<RepositoryFacts> {
  const entries = await readRootEntries(root);
  const tools = new Set<KnownTool>();

  for (const [entry, tool] of entryTools) {
    if (entries.includes(entry)) {
      tools.add(tool);
    }
  }

  const packageText = entries.includes("package.json")
    ? await readManifest({ root, relativePath: "package.json" })
    : null;
  const node =
    packageText === null ? null : detectNode({ entries, packageText });
  const python = hasPythonProject(entries)
    ? detectPython({
        entries,
        pyprojectText: await readManifest({
          root,
          relativePath: "pyproject.toml",
        }),
        requirementsText: await readManifest({
          root,
          relativePath: "requirements.txt",
        }),
      })
    : null;

  for (const tool of [...(node?.tools ?? []), ...(python?.tools ?? [])]) {
    tools.add(tool);
  }

  const makefile = entries.includes("Makefile")
    ? await readManifest({ root, relativePath: "Makefile" })
    : null;
  const ciWorkflows = await readManifestDirectory({
    root,
    relativePath: ".github/workflows",
    extensions: [".yml", ".yaml"],
    maximumFiles: 20,
  });

  return {
    root,
    entries,
    tools,
    node: node?.facts ?? null,
    python: python?.facts ?? null,
    rust: entries.includes("Cargo.toml"),
    go: entries.includes("go.mod"),
    makeTargets: makefile === null ? [] : makeTargets(makefile),
    ciWorkflows,
  };
}
