import path from "node:path";
import type { Integration } from "./types";

export class HiddenInstructionsError extends Error {
  readonly override: string;
  readonly hidden: string;
  readonly installed: boolean;

  constructor(options: {
    readonly override: string;
    readonly hidden: string;
    readonly installed: boolean;
  }) {
    super(
      options.installed
        ? `${options.override}, which Shadowclone created, hides ${options.hidden} from Codex`
        : `${options.override} would hide ${options.hidden} from Codex`,
    );
    this.name = "HiddenInstructionsError";
    this.override = options.override;
    this.hidden = options.hidden;
    this.installed = options.installed;
  }
}

export async function assertCodexOverrideHidesNothing(options: {
  readonly directory: string;
  readonly previous: Integration | undefined;
}): Promise<void> {
  const override = path.join(options.directory, "AGENTS.override.md");
  const hidden = path.join(options.directory, "AGENTS.md");
  const installed =
    options.previous?.files.some(
      (file) => file.relativePath === "AGENTS.override.md" && file.created,
    ) ?? false;

  if ((await Bun.file(hidden).exists()) && (installed || !(await Bun.file(override).exists()))) {
    throw new HiddenInstructionsError({ override, hidden, installed });
  }
}
