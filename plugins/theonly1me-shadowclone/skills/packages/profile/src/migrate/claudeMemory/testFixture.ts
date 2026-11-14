import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig, canonicalPath, createProjectPaths } from "@shadowclone/core";
import { claudeMemoryDirectory } from "./scan";
import type { ClaudeMemoryDecisions } from "./decisions";

function memory(options: {
  readonly name: string;
  readonly description: string;
  readonly type: "feedback" | "reference" | "project";
  readonly body: string;
}): string {
  return [
    "---",
    `name: ${options.name}`,
    `description: ${options.description}`,
    "metadata:",
    "  node_type: memory",
    `  type: ${options.type}`,
    "  modified: 2026-09-18T00:00:00.000Z",
    "---",
    "",
    options.body,
    "",
  ].join("\n");
}

export async function claudeMemoryFixture() {
  const home = canonicalPath(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-memory-")),
  );
  const repositoryRoot = path.join(home, "work", "sample-app");
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const directory = claudeMemoryDirectory({ paths, repositoryRoot });

  await mkdir(repositoryRoot, { recursive: true });
  await mkdir(directory, { recursive: true });
  await Bun.write(
    path.join(directory, "feedback_prefer_bun.md"),
    memory({
      name: "prefer-bun",
      description: "Prefer Bun for scripts",
      type: "feedback",
      body: "Use Bun for repository scripts.",
    }),
  );
  await Bun.write(
    path.join(directory, "reference_queue.md"),
    memory({
      name: "reference_queue",
      description: "Queue retry details",
      type: "reference",
      body: "Queue retries use a separate budget.",
    }),
  );
  await Bun.write(
    path.join(directory, "reference_obsolete.md"),
    memory({
      name: "reference_obsolete",
      description: "Obsolete detail",
      type: "reference",
      body: "This record is archive-only.",
    }),
  );
  await Bun.write(
    path.join(directory, "project_active.md"),
    memory({
      name: "project_active",
      description: "Active project work",
      type: "project",
      body: "See [[feedback_prefer_bun]] and [[reference_queue]].",
    }),
  );
  await Bun.write(
    path.join(directory, "MEMORY.md"),
    "# Memory Index\n\n- [Feedback](feedback_prefer_bun.md)\n",
  );
  await writeConfig({
    configPath: paths.configFile,
    config: {
      ...defaultConfig,
      sources: {
        ...defaultConfig.sources,
        "claude-memory": true,
        "git-metadata": true,
      },
    },
  });

  const decisions: ClaudeMemoryDecisions = {
    feedback: new Map([
      [
        "feedback_prefer_bun.md",
        {
          disposition: "rule",
          title: "Prefer Bun for scripts",
          scope: "project",
          section: "engineering",
        },
      ],
    ]),
    excludeReferences: new Set(["reference_obsolete.md"]),
  };

  return { home, repositoryRoot, paths, directory, decisions };
}
