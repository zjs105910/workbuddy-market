import type { ProfileFile } from "./files";

export function droppedProfileRuleKeys(options: {
  readonly files: readonly ProfileFile[];
  readonly written: ReadonlySet<string>;
  readonly retired: ReadonlySet<string>;
}): readonly string[] {
  return options.files.flatMap((file) =>
    file.blocks.flatMap((block) =>
      block.key !== null &&
      !options.written.has(block.key) &&
      !options.retired.has(block.key)
        ? [block.key]
        : [],
    ),
  );
}

export function assertProfileRetention(options: {
  readonly files: readonly ProfileFile[];
  readonly written: ReadonlySet<string>;
  readonly retired: ReadonlySet<string>;
}): void {
  const dropped = droppedProfileRuleKeys(options);

  if (dropped.length === 0) {
    return;
  }

  throw new Error(
    `Profile write would remove ${dropped.length} stored rule(s) without an explicit retirement`,
  );
}
