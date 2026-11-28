import type { HarnessFinding } from "./types";

export const refresh = "run `shadowclone sync`";

export function error(options: {
  readonly rule: string;
  readonly path: string;
  readonly fix: string;
}): HarnessFinding {
  return { severity: "error", line: null, ...options };
}

export function warning(options: {
  readonly rule: string;
  readonly path: string;
  readonly fix: string;
}): HarnessFinding {
  return { severity: "warning", line: null, ...options };
}
