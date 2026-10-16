import { gitIdentityArguments } from "./gitIdentity";
import { runProcess } from "./process";

const gitSafetyArguments = [
  "-c",
  "core.hooksPath=/dev/null",
  "-c",
  "core.fsmonitor=false",
  "-c",
  "core.pager=cat",
  "-c",
  "commit.gpgsign=false",
  "-c",
  "tag.gpgSign=false",
  "-c",
  "protocol.ext.allow=never",
  "-c",
  "protocol.file.allow=never",
];

export function hostEnvironment(
  options: { readonly remote?: boolean } = {},
): Record<string, string | undefined> {
  return {
    PATH: process.env.PATH,
    HOME: process.env.HOME,
    LANG: process.env.LANG,
    TMPDIR: process.env.TMPDIR,
    GIT_CONFIG_NOSYSTEM: "1",
    GIT_CONFIG_GLOBAL: "/dev/null",
    GIT_TERMINAL_PROMPT: "0",
    ...(options.remote
      ? {
          GH_TOKEN: process.env.GH_TOKEN,
          GITHUB_TOKEN: process.env.GITHUB_TOKEN,
          SSH_AUTH_SOCK: process.env.SSH_AUTH_SOCK,
        }
      : {}),
  };
}

export async function runHostCommand(options: {
  readonly arguments: readonly string[];
  readonly cwd: string;
  readonly timeoutSeconds?: number;
  readonly signal?: AbortSignal;
}) {
  const [executable, ...arguments_] = options.arguments;

  if (!executable) {
    throw new Error("Command requires an executable");
  }

  const remote = executable === "gh" || arguments_.includes("push");
  const environment = hostEnvironment({ remote });
  const safety = [...gitSafetyArguments];

  if (executable === "git" && !arguments_.includes("config")) {
    const configuration = await runProcess({
      arguments: [
        "git",
        ...safety,
        "config",
        "--local",
        "--includes",
        "--name-only",
        "--get-regexp",
        "^(filter\\..*\\.(clean|smudge|process|required)|diff\\..*\\.(command|textconv)|core\\.sshcommand|remote\\..*\\.(vcs|receivepack)|core\\.gitproxy|credential(\\..*)?\\.helper)$",
      ],
      cwd: options.cwd,
      environment,
      timeoutMilliseconds: 10_000,
      signal: options.signal,
    });

    if (configuration.stdout.trim().length > 0) {
      throw new Error(
        "Automatic Git commands refuse executable repository configuration",
      );
    }
  }

  if (executable === "git" && arguments_.includes("commit")) {
    safety.push(
      ...(await gitIdentityArguments({ cwd: options.cwd, environment })),
    );
  }

  if (executable === "git" && arguments_.includes("push")) {
    safety.push(
      "-c",
      "credential.helper=",
      "-c",
      "credential.https://github.com.helper=!gh auth git-credential",
    );
  }

  return runProcess({
    arguments:
      executable === "git"
        ? ["git", ...safety, ...arguments_]
        : [executable, ...arguments_],
    cwd: options.cwd,
    environment,
    timeoutMilliseconds: (options.timeoutSeconds ?? 60) * 1000,
    signal: options.signal,
  });
}
