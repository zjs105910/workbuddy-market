import path from "node:path";
import { format } from "prettier";
import { fingerprint, readLocalFile } from "@shadowclone/core";
import {
  bundledVersionIndex,
  bundledVersionsSchema,
  type BundledVersions,
} from "@shadowclone/skills";

type SkillFileVersion = {
  readonly skill: string;
  readonly file: string;
  readonly fingerprint: string;
};

const versionsFile = path.join("packages", "skills", "src", "skills", "bundledVersions.json");

async function currentVersions(rootDirectory: string): Promise<readonly SkillFileVersion[]> {
  const versions: SkillFileVersion[] = [];
  const skillsDirectory = path.join(rootDirectory, "skills");

  for await (const relativePath of new Bun.Glob("*/**/*").scan({
    cwd: skillsDirectory,
    onlyFiles: true,
  })) {
    const [skill = "", ...rest] = relativePath.split(path.sep);
    const file = rest.join("/");
    const text = await readLocalFile({
      filePath: path.join(skillsDirectory, relativePath),
      encoding: file === "SKILL.md" ? "utf8" : "base64",
    });

    if (text !== null) {
      versions.push({ skill, file, fingerprint: fingerprint(text) });
    }
  }

  return versions.sort((left, right) =>
    `${left.skill}/${left.file}`.localeCompare(`${right.skill}/${right.file}`),
  );
}

async function readVersions(rootDirectory: string): Promise<BundledVersions> {
  const text = await readLocalFile({ filePath: path.join(rootDirectory, versionsFile) });

  return bundledVersionsSchema.parse(JSON.parse(text ?? "{}"));
}

export async function unrecordedSkillVersions(
  rootDirectory: string,
): Promise<readonly SkillFileVersion[]> {
  const index = bundledVersionIndex(await readVersions(rootDirectory));

  return (await currentVersions(rootDirectory)).filter(
    (version) => !index.get(`${version.skill}/${version.file}`)?.has(version.fingerprint),
  );
}

export async function recordSkillVersions(rootDirectory: string): Promise<number> {
  const recorded = new Map(
    Object.entries(await readVersions(rootDirectory)).map(([skill, files]) => [
      skill,
      new Map(Object.entries(files)),
    ]),
  );
  const missing = await unrecordedSkillVersions(rootDirectory);

  for (const version of missing) {
    const files = recorded.get(version.skill) ?? new Map<string, string[]>();

    files.set(version.file, [...(files.get(version.file) ?? []), version.fingerprint]);
    recorded.set(version.skill, files);
  }

  const sorted = [...recorded.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([skill, files]) => [skill, Object.fromEntries(files)]);

  await Bun.write(
    path.join(rootDirectory, versionsFile),
    await format(JSON.stringify(Object.fromEntries(sorted)), { parser: "json", printWidth: 100 }),
  );

  return missing.length;
}

if (import.meta.main) {
  if (process.argv.includes("--record")) {
    const added = await recordSkillVersions(process.cwd());

    console.log(
      `skill versions: recorded ${added} new file version${added === 1 ? "" : "s"} in ${versionsFile}`,
    );
  } else {
    const missing = await unrecordedSkillVersions(process.cwd());

    for (const version of missing) {
      console.log(
        `skills/${version.skill}/${version.file} is not recorded in ${versionsFile}. Run bun run tooling/src/skillVersions.ts --record.`,
      );
    }

    console.log(
      `skill versions: found ${missing.length} unrecorded file${missing.length === 1 ? "" : "s"}`,
    );

    if (missing.length > 0) {
      process.exitCode = 1;
    }
  }
}
