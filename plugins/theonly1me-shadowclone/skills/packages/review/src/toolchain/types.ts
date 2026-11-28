export type Diagnostic = {
  readonly tool: string;
  readonly path: string;
  readonly line: number;
  readonly message: string;
};

export type DiagnosticScope = "changed-lines" | "changed-files" | "new-in-head";

export type ParserId = "colon" | "paren" | "maven" | "gradle" | "github" | "pyright" | "eslint-json" | "file-list";

export type StackContext = {
  readonly root: string;
  readonly changedFiles: readonly string[];
  readonly exists: (relativePath: string) => boolean;
  readonly read: (relativePath: string) => string;
};

export type ToolCommand = {
  readonly tool: string;
  readonly scope: DiagnosticScope;
  readonly parser: ParserId;
  readonly command: (context: StackContext) => readonly string[] | null;
};

export type Stack = {
  readonly id: string;
  readonly sources: RegExp;
  readonly detect: (context: StackContext) => boolean;
  readonly install: (context: StackContext) => readonly string[] | null;
  readonly commands: readonly ToolCommand[];
};

export type CommandStatus = "ran" | "skipped" | "failed" | "timed-out";

export type CommandReport = {
  readonly stack: string;
  readonly tool: string;
  readonly status: CommandStatus;
  readonly detail: string;
  readonly diagnostics: readonly Diagnostic[];
};
