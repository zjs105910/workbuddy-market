import { existsSync } from "node:fs";
import path from "node:path";
import { ProcessLimitError, runProcess } from "@shadowclone/core";

export type ToolRun =
  | { readonly kind: "finished"; readonly exitCode: number; readonly output: string }
  | { readonly kind: "timed-out" }
  | { readonly kind: "too-much-output" }
  | { readonly kind: "missing"; readonly executable: string };

const passedKeys = [
  "PATH",
  "HOME",
  "USER",
  "LOGNAME",
  "SHELL",
  "LANG",
  "LC_ALL",
  "TMPDIR",
  "TZ",
  "SSL_CERT_FILE",
  "NODE_EXTRA_CA_CERTS",
  "GOPATH",
  "GOROOT",
  "GOMODCACHE",
  "GOCACHE",
  "CARGO_HOME",
  "RUSTUP_HOME",
  "JAVA_HOME",
  "GRADLE_USER_HOME",
  "MAVEN_HOME",
  "DOTNET_ROOT",
  "NUGET_PACKAGES",
  "PNPM_HOME",
  "COREPACK_HOME",
  "BUN_INSTALL",
  "npm_config_cache",
  "VIRTUAL_ENV",
  "PYENV_ROOT",
] as const;

export function toolEnvironment(
  source: Readonly<Record<string, string | undefined>> = process.env,
): Record<string, string> {
  const environment: Record<string, string> = {
    CI: "1",
    NO_COLOR: "1",
    FORCE_COLOR: "0",
    DOTNET_CLI_TELEMETRY_OPTOUT: "1",
    DOTNET_NOLOGO: "1",
    NEXT_TELEMETRY_DISABLED: "1",
  };

  for (const key of passedKeys) {
    const value = source[key];

    if (value !== undefined) {
      environment[key] = value;
    }
  }

  return environment;
}

export async function runTool(options: {
  readonly arguments: readonly string[];
  readonly cwd: string;
  readonly timeoutMilliseconds: number;
}): Promise<ToolRun> {
  const [executable] = options.arguments;
  const environment = toolEnvironment();

  if (executable === undefined) {
    throw new Error("A toolchain command needs an executable");
  }

  const available = executable.includes("/")
    ? existsSync(path.join(options.cwd, executable))
    : Bun.which(executable, { PATH: environment.PATH ?? "" }) !== null;

  if (!available) {
    return { kind: "missing", executable };
  }

  try {
    const result = await runProcess({
      arguments: options.arguments,
      cwd: options.cwd,
      environment,
      timeoutMilliseconds: options.timeoutMilliseconds,
    });

    return { kind: "finished", exitCode: result.exitCode, output: `${result.stdout}\n${result.stderr}` };
  } catch (error) {
    if (!(error instanceof ProcessLimitError)) {
      throw error;
    }

    return error.message === "Process output limit exceeded" ? { kind: "too-much-output" } : { kind: "timed-out" };
  }
}
