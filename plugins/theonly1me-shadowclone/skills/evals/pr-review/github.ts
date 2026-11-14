import { runProcess } from "@shadowclone/core";

export async function ghJson(arguments_: readonly string[]): Promise<unknown> {
  const result = await runProcess({
    arguments: ["gh", ...arguments_],
    cwd: process.cwd(),
    environment: process.env,
    timeoutMilliseconds: 120_000,
  });

  if (result.exitCode !== 0) {
    throw new Error(`gh ${arguments_.slice(0, 3).join(" ")} failed: ${result.stderr.trim().slice(0, 300)}`);
  }

  return JSON.parse(result.stdout);
}

export async function inBatches<Input, Output>(options: {
  readonly items: readonly Input[];
  readonly size: number;
  readonly work: (item: Input) => Promise<Output>;
}): Promise<readonly Output[]> {
  const results: Output[] = [];

  for (let start = 0; start < options.items.length; start += options.size) {
    results.push(...(await Promise.all(options.items.slice(start, start + options.size).map(options.work))));
  }

  return results;
}
