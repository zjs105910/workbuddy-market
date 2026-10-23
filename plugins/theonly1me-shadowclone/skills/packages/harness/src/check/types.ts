export type HarnessFinding = {
  readonly severity: "error" | "warning";
  readonly rule: string;
  readonly path: string;
  readonly line: number | null;
  readonly fix: string;
};

export type HarnessCheckReport = {
  readonly checkedFiles: number;
  readonly findings: readonly HarnessFinding[];
};
