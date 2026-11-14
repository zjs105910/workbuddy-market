import path from "node:path";
import { harnessInitCommand } from "../harness";
import { acceptAll, type HarnessTestSetup } from "@shadowclone/harness/testing";

export const rules =
  "## Small files\n\nKeep every file under 200 lines, tests included.\n\n## Bun tests\n\nRun `bun test` before presenting.\n";

export function init(
  setup: HarnessTestSetup,
  options: {
    readonly personal?: boolean | null;
    readonly ask?: () => boolean;
  } = {},
) {
  return harnessInitCommand({
    apply: true,
    personal: options.personal ?? true,
    skills: [],
    enforceClaude: false,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    ask: options.ask ?? acceptAll,
    writeLine: () => undefined,
  });
}

export function read(
  setup: HarnessTestSetup,
  relativePath: string,
): Promise<string> {
  return Bun.file(path.join(setup.root, relativePath)).text();
}
