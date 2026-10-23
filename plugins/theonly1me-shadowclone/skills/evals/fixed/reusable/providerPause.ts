import type { NativeDiagnostic } from "../../native/diagnostics";
import type { RunRecord } from "../../native/study/record";

export function confirmedProviderPause(record: RunRecord): NativeDiagnostic | null {
  if (
    record.status !== "error" ||
    record.files.length > 0 ||
    record.commits.length > 0 ||
    record.toolCalls.length > 0 ||
    record.turns.length !== 1 ||
    record.turns.some(
      (turn) =>
        !turn.isError || turn.timedOut || turn.actions.length > 0 || turn.changedPaths.length > 0,
    )
  )
    return null;
  const message = record.error;
  if (
    !message ||
    !/^You've hit your (?:session|weekly) limit [·•] resets .+\([A-Za-z_]+\/[A-Za-z_]+\)$/u.test(
      message,
    )
  )
    return null;
  return {
    stage: "execution",
    confirmedInfrastructure: true,
    message: "Provider quota refused the request before agent work.",
    details: message,
  };
}
