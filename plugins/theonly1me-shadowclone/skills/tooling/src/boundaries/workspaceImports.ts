import type { ImportEdge } from "./imports";
import { browserSubpath } from "./browser";
import { packageOfFile, workspaceKeyOfFile } from "./layout";
import type { ManifestIndex } from "./manifests";
import { packageLayout, packageNames, type PackageLayout } from "./packages";
import { parseWorkspaceSpecifier, workspaceNameOf } from "./specifiers";

export type WorkspaceImportViolation = {
  readonly file: string;
  readonly line: number;
  readonly message: string;
};

export function workspaceImportViolations(options: {
  readonly edge: ImportEdge;
  readonly manifests: ManifestIndex;
  readonly isBrowserFile: boolean;
  readonly layout?: PackageLayout;
}): readonly WorkspaceImportViolation[] {
  const layout = options.layout ?? packageLayout;
  const { edge, manifests } = options;
  const parsed = parseWorkspaceSpecifier(edge.specifier);

  if (parsed === null) {
    return [];
  }

  const position = { file: edge.file, line: edge.line };
  const imported = packageNames.find((name) => name === parsed.packageName);
  const target = imported ? manifests.get(imported) : undefined;

  if (!imported || !target) {
    return [{ ...position, message: `"${edge.specifier}" is not a workspace package` }];
  }

  const violations: WorkspaceImportViolation[] = [];
  const workspace = workspaceKeyOfFile(edge.file);
  const declared = manifests.get(workspace)?.workspaceDependencies ?? [];

  if (!target.exportedSubpaths.includes(parsed.subpath)) {
    violations.push({
      ...position,
      message: `"${edge.specifier}" is not listed in the exports of ${workspaceNameOf(imported)}`,
    });
  }

  if (options.isBrowserFile && !edge.typeOnly && parsed.subpath !== browserSubpath) {
    violations.push({
      ...position,
      message: `"${edge.specifier}" is not a ${browserSubpath} subpath, and the web client must not load node code`,
    });
  }

  if (!declared.includes(workspaceNameOf(imported))) {
    violations.push({
      ...position,
      message: `${workspaceNameOf(imported)} is not declared in the package.json that owns this file`,
    });
  }

  if (workspace === "evals" || workspace === "tooling") {
    return violations;
  }

  const importer = packageOfFile(edge.file);

  if (importer === null) {
    violations.push({ ...position, message: "file belongs to no package" });
  } else if (importer === imported) {
    violations.push({
      ...position,
      message: `"${edge.specifier}" makes ${importer} import its own package`,
    });
  } else if (!layout.allowedDependencies[importer].includes(imported)) {
    violations.push({
      ...position,
      message: `"${edge.specifier}" makes ${importer} depend on ${imported}`,
    });
  }

  return violations;
}
