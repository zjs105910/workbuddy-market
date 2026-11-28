import type { KnownTool } from "@shadowclone/profile";

export type NodePackageManager = "bun" | "pnpm" | "yarn" | "npm";
export type PythonPackageManager = "uv" | "poetry" | "pip";

export type NodeFacts = {
  readonly packageManager: NodePackageManager;
  readonly scripts: Readonly<Record<string, string>>;
};

export type PythonFacts = {
  readonly packageManager: PythonPackageManager;
  readonly testRunner: "pytest" | "unittest";
  readonly hasRequirements: boolean;
};

export type RepositoryFacts = {
  readonly root: string;
  readonly entries: readonly string[];
  readonly tools: ReadonlySet<KnownTool>;
  readonly node: NodeFacts | null;
  readonly python: PythonFacts | null;
  readonly rust: boolean;
  readonly go: boolean;
  readonly makeTargets: readonly string[];
  readonly ciWorkflows: readonly string[];
};

export type HarnessCommand = {
  readonly label: "Install" | "Gate" | "Tests" | "Lint" | "Typecheck";
  readonly command: string;
};

export type HarnessGate = {
  readonly command: string;
  readonly source: string;
  readonly ciRunsGate: boolean;
};
