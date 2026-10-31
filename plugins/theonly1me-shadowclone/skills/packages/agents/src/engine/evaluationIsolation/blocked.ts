export type BlockedPath = {
  readonly path: string;
  readonly kind: "directory" | "file";
};

export function denySubpathRules(options: {
  readonly paths: readonly string[];
  readonly operations: readonly string[];
}): string {
  if (options.paths.length === 0) {
    return "";
  }

  const predicates = options.paths
    .map((target) => `(subpath ${JSON.stringify(target)})`)
    .join(" ");

  return options.operations
    .map((operation) => `(deny ${operation} ${predicates})`)
    .join("");
}

export function maskArguments(
  blocked: readonly BlockedPath[],
): readonly string[] {
  return blocked.flatMap((entry) =>
    entry.kind === "directory"
      ? ["--tmpfs", entry.path]
      : ["--ro-bind-try", "/dev/null", entry.path],
  );
}
