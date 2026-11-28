import { z } from "zod";

export const claudeSettingsPath = ".claude/settings.local.json";
export const stopHookCommand =
  "shadowclone check --changed --format claude-stop";

const settingsSchema = z
  .object({ hooks: z.record(z.string(), z.array(z.unknown())).optional() })
  .passthrough();
const stopEntry = {
  hooks: [{ type: "command", command: stopHookCommand, timeout: 60 }],
};

export function mergeClaudeStopHook(previous: string | null): string {
  let parsed: z.infer<typeof settingsSchema>;

  try {
    parsed = settingsSchema.parse(
      previous === null ? {} : JSON.parse(previous),
    );
  } catch {
    throw new Error("is not valid settings JSON, so it was left alone");
  }

  const hooks = parsed.hooks ?? {};
  const stop = hooks.Stop ?? [];

  if (
    previous !== null &&
    stop.some((entry) => JSON.stringify(entry) === JSON.stringify(stopEntry))
  ) {
    return previous;
  }

  return `${JSON.stringify({ ...parsed, hooks: { ...hooks, Stop: [...stop, stopEntry] } }, null, 2)}\n`;
}
