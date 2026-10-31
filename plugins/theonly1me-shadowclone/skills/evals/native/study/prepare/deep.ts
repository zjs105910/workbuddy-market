import { learn } from "@shadowclone/cli";
import type { EngineRunner } from "@shadowclone/agents";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";

export type DeepPass = {
  readonly pass: number;
  readonly remaining: number;
  readonly maintenance: string | null;
};

export function remainingEpisodes(lines: readonly string[]): number {
  for (const line of lines) {
    const match = /(\d+) remain\. Run shadowclone learn --deep again/.exec(line);

    if (match?.[1]) {
      return Number(match[1]);
    }
  }

  return 0;
}

export async function prepareDeep(options: {
  readonly learningPaths: ProjectPaths;
  readonly workspace: string;
  readonly runner: EngineRunner;
  readonly readRemote: GitRemoteReader;
  readonly maximumPasses: number;
  readonly callsPerPass: number;
  readonly writeLine: (line: string) => void;
}): Promise<readonly DeepPass[]> {
  const passes: DeepPass[] = [];

  for (let pass = 1; pass <= options.maximumPasses; pass += 1) {
    const output: string[] = [];

    await learn({
      paths: options.learningPaths,
      workingDirectory: options.workspace,
      deep: true,
      apply: true,
      engine: "codex",
      model: "gpt-6-sol",
      reasoningEffort: "medium",
      maximumCalls: options.callsPerPass,
      runner: options.runner,
      readRemote: options.readRemote,
      managedConfigPath: null,
      writeLine: (line) => {
        output.push(line);
        options.writeLine(line);
      },
    });

    const result = {
      pass,
      remaining: remainingEpisodes(output),
      maintenance: output.find((line) => line.startsWith("Skill maintenance:")) ?? null,
    };
    passes.push(result);

    if (result.remaining === 0) {
      return passes;
    }
  }

  throw new Error(`Deep learning backlog is unfinished after ${options.maximumPasses} passes; shorten the learning window`);
}
