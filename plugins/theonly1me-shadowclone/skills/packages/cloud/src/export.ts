import path from "node:path";
import { lstat, mkdtemp, rm } from "node:fs/promises";
import { environmentCompilation, materializeSkillDelivery } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import { resolveRepository, isOriginBlocked, type GitRemoteReader } from "@shadowclone/sessions";
import { readEffectiveConfig, ownedDirectory } from "@shadowclone/core";
import { deliveryFingerprint } from "./deliveryFiles";
import type { Delivery } from "./types";

export async function exportGuidance(options: {
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly skills: readonly string[];
  readonly readRemote?: GitRemoteReader;
}): Promise<Delivery> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath: options.paths.managedConfigFile,
  });

  if (!policy.enabled || !policy.allowedSources.includes("git-metadata")) {
    throw new Error("Managed policy disables Shadowclone.");
  }

  const repository = await resolveRepository({
    cwd: options.cwd,
    enabled: true,
    readRemote: options.readRemote,
  });

  if (!repository || isOriginBlocked({ repository, patterns: policy.blockedOrigins })) {
    throw new Error("The repository origin is unknown or blocked by managed policy.");
  }

  if (!options.skills.includes("shadowclone-work")) {
    throw new Error("Select shadowclone-work for cloud work.");
  }

  await ownedDirectory(path.join(options.paths.shadowcloneDirectory, "cloud"));

  const temporary = await mkdtemp(
    path.join(options.paths.shadowcloneDirectory, "cloud", "export-"),
  );
  const files: Delivery["files"][number][] = [];
  const found = new Set<string>();

  try {
    const routing = await materializeSkillDelivery({
      paths: options.paths,
      repositoryDirectory: options.cwd,
      destination: temporary,
      selectedNames: options.skills,
      includeLibrary: config.sources["skill-library"],
      repository,
      onArtifact: async ({ source, destination }) => {
        const [, , name, ...relative] = path.relative(temporary, destination).split(path.sep);

        if (!name || !/^[a-z0-9-]+$/.test(name)) {
          throw new Error("The skill name is not portable.");
        }

        if (
          relative.some((part) => [".git", ".shadowclone", "sessions", "receipts"].includes(part))
        ) {
          throw new Error("The selection contains private state.");
        }

        const resource = `plugins/shadowclone-personal/skills/${name}/${relative.join("/")}`;

        if (files.some((file) => file.path === resource)) {
          throw new Error("Select one source for each skill name.");
        }

        const content = Buffer.from(await Bun.file(destination).arrayBuffer());
        const text = content.toString("utf8");

        if (
          /\/Users\/|\/home\/|\/private\/|[A-Za-z]:\\/u.test(text) ||
          text.includes(options.cwd)
        ) {
          throw new Error(
            `Remove identifying local paths from ${name}/${relative.join("/")} before export.`,
          );
        }

        files.push({
          path: resource,
          content: content.toString("base64"),
          mode: (await lstat(source)).mode & 0o777,
        });

        if (relative.join("/") === "SKILL.md") {
          found.add(name);
        }
      },
    });

    if (routing === null) {
      throw new Error("Activate a skills environment with shadowclone init before exporting.");
    }

    if (options.skills.some((name) => !found.has(name))) {
      throw new Error("A selected skill is not available in this repository scope.");
    }

    const native = (
      await environmentCompilation({
        paths: options.paths,
        cwd: options.cwd,
        originDirectory: repository.origin.directoryName,
        repositoryName: repository.profileFileName,
      })
    )?.markdown;

    if (
      !native ||
      /\/Users\/|\/home\/|\/private\/|[A-Za-z]:\\/u.test(native) ||
      native.includes(options.cwd)
    ) {
      throw new Error("The native rules contain identifying paths or are disabled.");
    }

    const addText = (options_: { path: string; content: string }) =>
      files.push({
        path: options_.path,
        content: Buffer.from(options_.content).toString("base64"),
        mode: 0o600,
      });

    addText({
      path: ".claude-plugin/marketplace.json",
      content: JSON.stringify({
        name: "shadowclone-personal",
        owner: { name: "Personal clone" },
        plugins: [
          {
            name: "shadowclone-personal",
            source: "./plugins/shadowclone-personal",
          },
        ],
      }),
    });

    addText({
      path: "plugins/shadowclone-personal/.claude-plugin/plugin.json",
      content: JSON.stringify({
        name: "shadowclone-personal",
        version: "1.0.0",
        description: "Reviewed personal engineering skills",
      }),
    });

    addText({ path: "native.md", content: native });

    return {
      native,
      files,
      skills: [...found],
      fingerprint: deliveryFingerprint(files),
    };
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}
