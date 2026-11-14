import type { FakeState, Workspace } from "./state";

export type CommandContext = {
  readonly workspace: Workspace;
  readonly state: FakeState;
  readonly cwd: string;
  readonly args: readonly string[];
};

export type CommandOutcome = {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
  readonly operation: string;
  readonly supported: boolean;
  readonly details: Readonly<Record<string, unknown>>;
};

export function succeed(options: {
  readonly operation: string;
  readonly stdout: string;
  readonly details?: Readonly<Record<string, unknown>>;
}): CommandOutcome {
  return {
    stdout: options.stdout,
    stderr: "",
    exitCode: 0,
    operation: options.operation,
    supported: true,
    details: options.details ?? {},
  };
}

export function fail(options: {
  readonly operation: string;
  readonly message: string;
  readonly exitCode?: number;
  readonly details?: Readonly<Record<string, unknown>>;
}): CommandOutcome {
  return {
    stdout: "",
    stderr: `${options.message}\n`,
    exitCode: options.exitCode ?? 1,
    operation: options.operation,
    supported: true,
    details: options.details ?? {},
  };
}

export function unsupported(args: readonly string[]): CommandOutcome {
  return {
    stdout: "",
    stderr: `gh: this local GitHub stand-in does not support \`gh ${args.join(" ")}\`\n`,
    exitCode: 1,
    operation: "unsupported",
    supported: false,
    details: {},
  };
}
