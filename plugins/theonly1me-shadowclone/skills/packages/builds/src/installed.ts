import path from "node:path";
import { fingerprint, readLocalText } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import { parseSkillDocument } from "@shadowclone/skills";
import type { BuildDefinition, EnvironmentArtifact } from "@shadowclone/environment";
import type { BuildItem } from "./types";
import { skillClassification } from "./classification";

export async function installedBuildItem(options: {
  readonly build: BuildDefinition;
  readonly artifacts: readonly EnvironmentArtifact[];
  readonly original?: BuildItem;
}): Promise<BuildItem | null> {
  const copies = [];

  for (const artifact of options.artifacts) {
    const text = await readLocalText(artifact.filePath);

    if (text !== null) {
      copies.push({ artifact, text });
    }
  }

  const changed = copies.filter(
    ({ artifact, text }) => fingerprint(text) !== artifact.fingerprint,
  );

  if (new Set(changed.map(({ text }) => text)).size > 1) {
    throw new Error(
      "Skill copies have conflicting edits; reconcile them before opening the editor",
    );
  }

  const current =
    changed[0] ??
    copies.find(({ artifact }) =>
      artifact.filePath.includes("/.agents/skills/"),
    ) ??
    copies[0];

  if (!current?.artifact.buildEntryId) {
    return null;
  }

  const { artifact, text } = current;
  const id = current.artifact.buildEntryId;
  const { metadata, body } = parseSkillDocument(text);
  const classification = skillClassification(text);
  const directory = path.dirname(path.dirname(artifact.filePath));

  return {
    id,
    name: metadata.name,
    title: options.original?.title ?? metadata.name.replaceAll("-", " "),
    description: metadata.description,
    text,
    kind: "skill",
    category: options.original?.category ?? classification.category,
    section: options.original?.section ?? classification.section,
    axis: options.original?.axis ?? classification.axis,
    alwaysOn: options.original?.alwaysOn ?? false,
    owner: "managed",
    source: {
      id,
      root: {
        id: fingerprint(directory),
        directory,
        cwd: options.build.directory,
        scope: options.build.scope === "global" ? "global" : "repository",
        owner: "user",
        destination: directory,
        enabled: true,
      },
      relativePath: path.relative(directory, artifact.filePath),
      raw: text,
      redacted: redactSecrets({ text }),
      fingerprint: fingerprint(text),
      name: metadata.name,
      description: metadata.description,
      body,
    },
  };
}
