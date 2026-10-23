export type WorkspaceSpecifier = {
  readonly packageName: string;
  readonly subpath: string;
};

const workspaceScope = "@shadowclone/";

export function parseWorkspaceSpecifier(specifier: string): WorkspaceSpecifier | null {
  if (!specifier.startsWith(workspaceScope)) {
    return null;
  }

  const [packageName = "", ...rest] = specifier.slice(workspaceScope.length).split("/");

  return { packageName, subpath: rest.length === 0 ? "." : `./${rest.join("/")}` };
}

export function workspaceNameOf(packageName: string): string {
  return `${workspaceScope}${packageName}`;
}
