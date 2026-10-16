import { runHostCommand } from "./hostCommand";
export type CommandResult = {
  readonly exitCode: number;
  readonly stdout: string;
};

export type CommandRunner = (options: {
  readonly command: readonly string[];
  readonly cwd: string;
}) => Promise<CommandResult>;

export async function runCommand(options: {
  readonly command: readonly string[];
  readonly cwd: string;
}): Promise<CommandResult> {
  return runHostCommand({ arguments: options.command, cwd: options.cwd });
}
