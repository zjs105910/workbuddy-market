import { cp, lstat, mkdir } from "node:fs/promises";
import path from "node:path";
import { fingerprint, readLocalText, readEffectiveConfig } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { discoverDeliverySkills, readMaintenanceState } from "@shadowclone/skills";
import { readIntegrations } from "../integrations/state";
import { integrationFilePath } from "../integrations/targets";

export async function freezeOriginalEnvironment(
  paths: ProjectPaths,
): Promise<string> {
  const directory = path.join(
    paths.shadowcloneDirectory,
    "environment-baselines",
    crypto.randomUUID(),
  );
  const maintenance = await readMaintenanceState(paths);
  const { config } = await readEffectiveConfig({
    configPath: paths.configFile,
    managedConfigPath: paths.managedConfigFile,
  });
  const discovered = await discoverDeliverySkills(
    maintenance.roots.filter(
      (root) => root.enabled && config.sources["skill-library"],
    ),
  );
  let bytes = 0;

  const files: {
    readonly source: string;
    readonly relativePath: string;
    readonly hash: string;
    readonly scope?: string;
    readonly cwd?: string | null;
  }[] = [];

  for (const skill of discovered.skills) {
    const root = path.dirname(
      path.join(skill.root.directory, skill.relativePath),
    );

    for await (const relativePath of new Bun.Glob("**/*").scan({
      cwd: root,
      dot: true,
      onlyFiles: false,
      followSymlinks: false,
    })) {
      const source = path.join(root, relativePath);
      const metadata = await lstat(source);

      if (metadata.isSymbolicLink()) {
        throw new Error("Baseline skills contain a symbolic link");
      }

      if (metadata.isDirectory()) {
        continue;
      }

      if (!metadata.isFile()) {
        throw new Error("Baseline skills contain an unsupported file");
      }

      bytes += metadata.size;

      if (bytes > 64_000_000) {
        throw new Error(
          "Original environment exceeds the 64 MB snapshot limit",
        );
      }

      files.push({
        source,
        relativePath: path.join("skills", skill.id, relativePath),
        hash: new Bun.CryptoHasher("sha256")
          .update(await Bun.file(source).arrayBuffer())
          .digest("hex"),
      });
    }
  }

  for (const integration of config.sources["agent-context"]
    ? await readIntegrations(paths)
    : []) {
    for (const file of integration.files) {
      const source = integrationFilePath({ integration, file });
      const text = await readLocalText(source);

      if (text !== null) {
        files.push({
          source,
          relativePath: `integrations/${integration.id}/${file.relativePath.replaceAll("../", "parent/")}`,
          hash: fingerprint(text),
          scope: integration.scope,
          cwd:
            integration.scope === "repository" ? integration.directory : null,
        });
      }
    }
  }

  const home = path.dirname(paths.shadowcloneDirectory);

  const instructions = [
    ...[
      ".claude/CLAUDE.md",
      ".codex/AGENTS.md",
      ".codex/AGENTS.override.md",
    ].map((relative) => ({
      source: path.join(home, relative),
      scope: "global",
      cwd: null,
    })),
    ...[
      ...new Set(
        maintenance.roots
          .filter((root) => root.enabled && root.scope === "repository")
          .map((root) => root.cwd),
      ),
    ].flatMap((cwd) =>
      cwd
        ? ["AGENTS.md", "CLAUDE.md"].map((name) => ({
            source: path.join(cwd, name),
            scope: "repository",
            cwd,
          }))
        : [],
    ),
  ];

  for (const instruction of config.sources["agent-context"]
    ? instructions
    : []) {
    if (files.some((file) => file.source === instruction.source)) {
      continue;
    }

    const content = await readLocalText(instruction.source);

    if (content !== null) {
      files.push({
        ...instruction,
        relativePath: `instructions/${files.length}/${path.basename(instruction.source)}`,
        hash: fingerprint(content),
      });
    }
  }

  await mkdir(directory, { recursive: true, mode: 0o700 });

  for (const file of files) {
    const destination = path.join(directory, file.relativePath);

    await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
    await cp(file.source, destination, { errorOnExist: true });

    if (
      new Bun.CryptoHasher("sha256")
        .update(await Bun.file(destination).arrayBuffer())
        .digest("hex") !== file.hash
    ) {
      throw new Error(
        "Original environment changed during the snapshot; retry before publication",
      );
    }
  }

  await Bun.write(
    path.join(directory, "manifest.json"),
    `${JSON.stringify({ version: 1, files, skills: discovered.skills.map(({ id, name, description, root }) => ({ id, name, description, scope: root.scope, cwd: root.cwd })) }, null, 2)}\n`,
    { mode: 0o600 },
  );

  return directory;
}
