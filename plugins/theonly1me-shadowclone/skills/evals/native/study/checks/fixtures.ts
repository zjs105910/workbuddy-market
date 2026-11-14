import { pendingRun, type RunRecord, type StudyAction, type TurnRecord } from "../record";

export function turn(options: { index: number; response?: string; actions?: readonly StudyAction[]; commits?: TurnRecord["commits"]; branch?: string | null }): TurnRecord {
  return {
    index: options.index, response: options.response ?? "", actions: [...(options.actions ?? [])], skillReads: [], changedPaths: [],
    commits: [...(options.commits ?? [])], branch: options.branch ?? null, resolvedModel: "gpt-6-sol", durationMs: 1,
    costUsd: null, usage: null, isError: false, timedOut: false, error: null,
  };
}

export function run(options: Partial<RunRecord> & { turns: readonly TurnRecord[] }): RunRecord {
  const base = pendingRun({ arm: "bare", taskId: "synthetic", repeat: 0 });
  const turns = [...options.turns];
  return { ...base, ...options, turns, status: options.status ?? "complete", commits: options.commits ?? turns.at(-1)?.commits ?? [] };
}

export const edit = (path: string): StudyAction => ({ tool: "Edit", path, command: null, succeeded: true });
export const testRun = (succeeded: boolean): StudyAction => ({ tool: "Bash", path: null, command: "bun test test/retry.test.ts", succeeded });
