export const ecosystems = ["npm", "PyPI", "Go", "crates.io", "RubyGems", "Packagist", "NuGet"] as const;

export type Ecosystem = (typeof ecosystems)[number];

export type LockedPackage = {
  readonly ecosystem: Ecosystem;
  readonly name: string;
  readonly version: string;
};

export function packageKey(lockedPackage: LockedPackage): string {
  return `${lockedPackage.ecosystem}|${lockedPackage.name}|${lockedPackage.version}`;
}
