import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import { fingerprint } from "@shadowclone/core";
import { parseProfileBlocks } from "@shadowclone/profile";
import { splitProfileBlocks } from "@shadowclone/profile";
import { profileVisibleParts, stripProfileMetadata } from "@shadowclone/profile";
import { learningRuleSchema, type LearningRecord } from "./types";

export async function legacyManualLearning(
  paths: ProjectPaths,
): Promise<readonly LearningRecord[]> {
  const records: LearningRecord[] = [];

  const files = await Array.fromAsync(
    new Bun.Glob("{global,org}/**/*.md").scan({
      cwd: paths.profileDirectory,
      onlyFiles: true,
      followSymlinks: false,
    }),
  ).catch(() => []);

  for (const relativePath of files.sort()) {
    const segments = relativePath.split(path.sep);
    const filename = segments.at(-1) ?? "";
    const section = filename.replace(/\.md$/, "");

    const location =
      segments[0] === "global" && segments.length === 2
        ? { scope: "global", originDirectory: null, repositoryName: null }
        : segments[0] === "org" && segments.length === 3
          ? { scope: "org", originDirectory: segments[1], repositoryName: null }
          : segments[0] === "org" &&
              segments[2] === "projects" &&
              segments.length === 4
            ? {
                scope: "project",
                originDirectory: segments[1],
                repositoryName: section,
              }
            : null;

    if (
      !location ||
      (location.scope !== "project" &&
        !["identity", "engineering", "workflow", "boundaries"].includes(
          section,
        ))
    ) {
      continue;
    }

    const snapshot = await materializeSnapshot({
      filePath: path.join(paths.profileDirectory, relativePath),
      roots: [paths.profileDirectory],
      maximumBytes: 2_000_000,
      parse: parseProfileBlocks,
    });

    if (snapshot === null) {
      throw new Error(
        "Legacy profile could not be read safely during migration",
      );
    }

    const blocks = splitProfileBlocks(snapshot.redacted);

    for (const [index, block] of snapshot.parsed.entries()) {
      const visible = blocks[index];

      if (block.key !== null || !visible) {
        continue;
      }

      const { title, body } = profileVisibleParts(visible);

      if (!body && visible.trim().startsWith("#")) {
        continue;
      }

      records.push({
        kind: "guidance",
        sourceHash: fingerprint(visible),
        sourceLocator: relativePath,
        rule: learningRuleSchema.parse({
          ...location,
          key: `legacy-manual:${fingerprint(`${relativePath}/${index}/${title}`).slice(0, 24)}`,
          title,
          body: body || stripProfileMetadata(visible),
          section: ["workflow", "boundaries"].includes(section)
            ? section
            : "engineering",
          source: "user",
          status: "active",
          proposal: null,
          appliesWhen: [],
          evidence: { for: [], against: [] },
          observations: 0,
          sessions: 0,
          lastSeen: "legacy",
          origins: [],
          importReference: null,
        }),
      });
    }
  }

  return records;
}
