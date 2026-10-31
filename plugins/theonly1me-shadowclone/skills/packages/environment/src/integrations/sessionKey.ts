import { fingerprint } from "@shadowclone/core";

export function learningSessionKey(options: {
  readonly agent: string;
  readonly nativeSessionId: string;
}): string {
  return fingerprint(`${options.agent}:${options.nativeSessionId}`);
}
