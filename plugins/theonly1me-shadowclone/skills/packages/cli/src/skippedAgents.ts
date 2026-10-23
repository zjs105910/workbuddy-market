import { HiddenInstructionsError } from "@shadowclone/environment";
import { UnsafeDestinationError } from "@shadowclone/core";
import type { NativeInstallOptions } from "./nativeOptions";

type Agent = NativeInstallOptions["agents"][number];

export type SkippedAgent =
  | {
      readonly agent: Agent;
      readonly kind: "link";
      readonly path: string;
      readonly target: string | null;
    }
  | {
      readonly agent: Agent;
      readonly kind: "hidden";
      readonly override: string;
      readonly hidden: string;
      readonly installed: boolean;
    };

export function skippedAgentFrom(options: {
  readonly agent: Agent;
  readonly error: unknown;
  readonly skipUnsafeDestinations: boolean;
}): SkippedAgent | null {
  const { agent, error } = options;

  if (error instanceof HiddenInstructionsError) {
    return {
      agent,
      kind: "hidden",
      override: error.override,
      hidden: error.hidden,
      installed: error.installed,
    };
  }

  return options.skipUnsafeDestinations && error instanceof UnsafeDestinationError
    ? { agent, kind: "link", path: error.path, target: error.target }
    : null;
}

export function describeSkippedAgent(skipped: SkippedAgent): string {
  if (skipped.kind === "hidden") {
    const problem = skipped.installed
      ? `${skipped.override}, which Shadowclone created, hides the team file ${skipped.hidden}`
      : `${skipped.override} would hide the team file ${skipped.hidden}`;
    const action = skipped.installed
      ? "Run shadowclone uninstall --agent codex --local to remove it, and use shadowclone install --agent codex --global instead."
      : "Use shadowclone install --agent codex --global instead.";

    return `Not installed for ${skipped.agent}: ${problem}, because Codex reads one instruction file in each folder. ${action}`;
  }

  const reason =
    skipped.target === null
      ? `${skipped.path} is not a regular file`
      : `${skipped.path} is a symbolic link to ${skipped.target}`;

  return `Not installed for ${skipped.agent}: ${reason}. Shadowclone does not write through links, so ${skipped.agent} gets no Shadowclone guidance. Replace the link with a regular file, then run shadowclone install --agent ${skipped.agent}.`;
}
