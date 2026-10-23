import {
  renderCheckReport,
  repositoryRoot,
  runHarnessCheck,
  type CheckFormat,
} from "@shadowclone/harness";
import { canonicalPath } from "@shadowclone/core";
import { parseHookInput, readHookString } from "./hookInput";

export type HarnessCheckOptions = {
  readonly changed: boolean;
  readonly format: CheckFormat;
};

export function parseHarnessCheck(
  arguments_: readonly string[],
): HarnessCheckOptions | null {
  let changed = false;
  let format: CheckFormat = "human";

  for (let position = 0; position < arguments_.length; position += 1) {
    const argument = arguments_[position];

    if (argument === "--changed") {
      changed = true;
    } else if (argument === "--format") {
      const value = arguments_[++position];

      if (value !== "human" && value !== "json" && value !== "claude-stop") {
        return null;
      }

      format = value;
    } else {
      return null;
    }
  }

  return { changed, format };
}

export async function harnessCheckCommand(
  options: HarnessCheckOptions & {
    readonly cwd?: string;
    readonly stdin?: string;
    readonly write?: (options: {
      readonly stdout: string;
      readonly stderr: string;
    }) => Promise<void>;
  },
): Promise<number> {
  let cwd = options.cwd ?? process.cwd();

  if (options.format === "claude-stop") {
    const input = parseHookInput(options.stdin ?? (await Bun.stdin.text()));

    if (input.stop_hook_active === true) {
      return 0;
    }

    cwd = readHookString(input, "cwd") ?? cwd;
  }

  const root = await repositoryRoot({ cwd: canonicalPath(cwd) });
  const rendered = renderCheckReport({
    report: await runHarnessCheck({ root, changed: options.changed }),
    format: options.format,
  });

  await (options.write ?? writeStreams)({
    stdout: rendered.stdout,
    stderr: rendered.stderr,
  });

  return rendered.exitCode;
}

async function writeStreams(options: {
  readonly stdout: string;
  readonly stderr: string;
}): Promise<void> {
  if (options.stdout.length > 0) {
    await Bun.write(Bun.stdout, options.stdout);
  }

  if (options.stderr.length > 0) {
    await Bun.write(Bun.stderr, `${options.stderr}\n`);
  }
}
