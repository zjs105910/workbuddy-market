import { canonicalPath } from "@shadowclone/core";
import { denySubpathRules, maskArguments } from "./blocked";
import type { EngineRunOptions } from "../types";

export function evaluationCommand(options: {
  readonly arguments: readonly string[];
  readonly run: EngineRunOptions;
  readonly platform?: NodeJS.Platform;
  readonly temporaryDirectory?: string;
}): readonly string[] {
  if (options.run.execution.purpose !== "evaluation") {
    return options.arguments;
  }

  const requestedPaths = options.run.execution.blockedPaths ?? [];

  const platform = options.platform ?? process.platform;
  const blockedPaths = requestedPaths.map(canonicalPath);
  const directory = canonicalPath(options.run.cwd);
  const temporary = options.temporaryDirectory
    ? canonicalPath(options.temporaryDirectory)
    : null;

  if (platform === "darwin") {
    const writablePaths = [directory, ...(temporary ? [temporary] : [])]
      .map((entry) => `(subpath ${JSON.stringify(entry)})`)
      .join("");
    const sandboxProfile = `(version 1)(allow default)(deny file-write*)(allow file-write* ${writablePaths}(literal "/dev/null"))${denySubpathRules(
      {
        paths: blockedPaths,
        operations: ["file-read*", "file-write*"],
      },
    )}`;

    return ["sandbox-exec", "-p", sandboxProfile, ...options.arguments];
  }

  if (platform === "linux") {
    return [
      "bwrap",
      "--die-with-parent",
      "--unshare-pid",
      "--unshare-ipc",
      "--new-session",
      "--cap-drop",
      "ALL",
      "--ro-bind",
      "/",
      "/",
      "--bind",
      directory,
      directory,
      ...(temporary ? ["--bind", temporary, temporary] : []),
      "--proc",
      "/proc",
      "--dev",
      "/dev",
      ...maskArguments(
        blockedPaths.map((directory) => ({
          path: directory,
          kind: "directory" as const,
        })),
      ),
      "--",
      ...options.arguments,
    ];
  }

  throw new Error("Evaluation isolation requires macOS or Linux");
}
