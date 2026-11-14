import type { ExistingProfileRule, ProfileRule, ProfileSection } from "./types";

function profileSection(value: string): ProfileSection | null {
  if (
    value === "engineering" ||
    value === "workflow" ||
    value === "boundaries"
  ) {
    return value;
  }

  return null;
}

export function locatedRule(options: {
  readonly existing: ExistingProfileRule;
  readonly relativePath: string;
}): ProfileRule | null {
  const segments = options.relativePath.split("/");
  const filename = segments.at(-1) ?? "";
  const sectionName = filename.replace(/\.md$/, "");
  const section = profileSection(sectionName);
  const fields = { ...options.existing, section: "engineering" as const };

  if (segments[0] === "global" && segments.length === 2 && section !== null) {
    return {
      ...fields,
      section,
      scope: "global",
      originDirectory: null,
      repositoryName: null,
    };
  }

  const originDirectory = segments[1];

  if (!originDirectory || segments[0] !== "org") {
    return null;
  }

  if (segments.length === 3 && section !== null) {
    return {
      ...fields,
      section,
      scope: "org",
      originDirectory,
      repositoryName: null,
    };
  }

  if (
    segments.length === 4 &&
    segments[2] === "projects" &&
    filename.endsWith(".md")
  ) {
    return {
      ...fields,
      scope: "project",
      originDirectory,
      repositoryName: sectionName,
    };
  }

  return null;
}
