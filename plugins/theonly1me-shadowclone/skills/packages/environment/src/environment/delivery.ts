import path from "node:path";
import { mkdir, lstat } from "node:fs/promises";
import type { ProjectPaths } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import { readRedactedEnvironment } from "./store";
import { learningScopes } from "./scope";
import { renderSkillRouting } from "./context";
import { publishedSkills } from "./catalog";
import { assertRegularDestination } from "@shadowclone/core";
import { discoverDeliverySkills, readMaintenanceState } from "@shadowclone/skills";
import type { RepositoryIdentity } from "@shadowclone/sessions";

export async function materializeSkillDelivery(options: {
  readonly paths: ProjectPaths;
  readonly repositoryDirectory: string;
  readonly destination: string;
  readonly repository?: RepositoryIdentity;
  readonly includeLibrary?: boolean;
  readonly selectedNames?: readonly string[];
  readonly onArtifact?: (artifact: {
    readonly source: string;
    readonly destination: string;
  }) => Promise<void>;
}): Promise<string | null> {
  const state = await readRedactedEnvironment(options.paths);

  if (state?.phase !== "active") {
    return null;
  }

  const scopes = learningScopes({ paths: options.paths, state }).filter(
    (scope) =>
      scope.repository === null ||
      ((!options.repository ||
        (scope.repository.originDirectory === options.repository.origin.directoryName &&
          scope.repository.repositoryName === options.repository.profileFileName)) &&
        (path.resolve(options.repositoryDirectory) === scope.directory ||
          path.resolve(options.repositoryDirectory).startsWith(`${scope.directory}${path.sep}`))),
  );

  const scopeKeys = new Set(scopes.map(({ key }) => key));
  let routing = renderSkillRouting({ state, scopes });

  const roots = (await readMaintenanceState(options.paths)).roots.filter(
    (root) =>
      options.includeLibrary !== false &&
      root.enabled &&
      (root.scope === "global" || scopes.some((scope) => scope.directory === root.cwd)),
  );

  const library = await discoverDeliverySkills(roots);

  const skills = [
    ...new Map([
      ...publishedSkills({ state, scopes: scopeKeys }).map(
        (skill) =>
          [
            skill.filePath,
            {
              filePath: skill.filePath,
              name: skill.name,
              description: skill.description,
            },
          ] as const,
      ),
      ...library.skills.map(
        (skill) =>
          [
            path.join(skill.root.directory, skill.relativePath),
            {
              filePath: path.join(skill.root.directory, skill.relativePath),
              name: skill.name,
              description: skill.description,
            },
          ] as const,
      ),
    ]).values(),
  ];

  const catalog = [];
  let bytes = 0;

  for (const [position, skill] of skills.entries()) {
    if (options.selectedNames && !options.selectedNames.includes(skill.name)) {
      continue;
    }

    const sourceRoot = path.dirname(skill.filePath);

    assertRegularDestination(skill.filePath);

    const targetRoot = path.join(
      options.destination,
      ".shadowclone-skills",
      String(position),
      skill.name,
    );

    for await (const relativePath of new Bun.Glob("**/*").scan({
      cwd: sourceRoot,
      dot: true,
      onlyFiles: false,
      followSymlinks: false,
    })) {
      const filePath = path.join(sourceRoot, relativePath);
      const metadata = await lstat(filePath);

      if (metadata.isSymbolicLink()) {
        throw new Error("Skill delivery cannot follow symbolic links");
      }

      if (metadata.isDirectory()) {
        continue;
      }

      if (!metadata.isFile()) {
        throw new Error("Skill delivery encountered an unsupported file");
      }

      bytes += metadata.size;

      if (bytes > 64_000_000 || metadata.size > 8_000_000) {
        throw new Error("Skill delivery exceeds the snapshot budget");
      }

      const content = new Uint8Array(await Bun.file(filePath).arrayBuffer());
      let text: string | null = null;

      try {
        text = new TextDecoder("utf-8", { fatal: true }).decode(content);
      } catch {
        text = null;
      }

      const snapshot =
        text === null
          ? null
          : await materializeSnapshot({
              filePath,
              roots: [sourceRoot],
              maximumBytes: 2_000_000,
              parse: () => null,
            });

      if (text !== null && snapshot === null) {
        throw new Error("A published skill disappeared during delivery");
      }

      const destination = path.join(targetRoot, relativePath);

      await mkdir(path.dirname(destination), { recursive: true });
      await Bun.write(destination, snapshot?.redacted ?? content, {
        mode: metadata.mode & 0o777,
      });
      await options.onArtifact?.({ source: filePath, destination });
    }

    routing = routing.replaceAll(skill.filePath, path.join(targetRoot, "SKILL.md"));
    catalog.push({
      name: skill.name,
      description: skill.description,
      path: path.join(targetRoot, "SKILL.md"),
    });
  }

  return `${routing}\nAvailable skills (read selected bodies when needed):\n${JSON.stringify(catalog)}\n`;
}
