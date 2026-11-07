import type { WorkspaceKey } from "./manifests";
import { packageNames, type PackageName } from "./packages";

const packagesRoot = "packages";

export function packageOfFile(file: string): PackageName | null {
  const [root, name, ...rest] = file.split("/");
  const known = packageNames.find((packageName) => packageName === name);

  return root === packagesRoot && known && rest.length > 0 ? known : null;
}

export function workspaceKeyOfFile(file: string): WorkspaceKey {
  const folder = packageOfFile(file);

  if (folder) {
    return folder;
  }

  const [first] = file.split("/");

  return first === "evals" || first === "tooling" ? first : "root";
}
