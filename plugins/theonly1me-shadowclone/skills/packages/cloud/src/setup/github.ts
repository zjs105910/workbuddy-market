export type GithubApi = (options: {
  readonly route: string;
  readonly token?: string;
  readonly body?: unknown;
}) => Promise<unknown>;

export const githubApi: GithubApi = async (options) => {
  const [method, pathname] = options.route.split(" ");

  if (!method || !pathname?.startsWith("/")) {
    throw new Error("The GitHub API route is invalid.");
  }

  const response = await fetch(`https://api.github.com${pathname}`, {
    method,
    headers: {
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
      "Content-Type": "application/json",
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(30_000),
  });

  if (!response.ok) {
    throw new Error(
      `GitHub rejected the operation (${response.status}). Check account access and installation policy.`,
    );
  }

  return response.json();
};

export type GhCommand = (options: {
  readonly arguments: readonly string[];
  readonly input?: string;
}) => Promise<string>;

export const runGh: GhCommand = async (options) => {
  const executable = Bun.which("gh");

  if (!executable) {
    throw new Error("Install GitHub CLI and run gh auth login before setup.");
  }

  const child = Bun.spawn([executable, ...options.arguments], {
    stdin: options.input === undefined ? "ignore" : new Blob([options.input]),
    stdout: "pipe",
    stderr: "ignore",
  });
  const output = await new Response(child.stdout).text();

  if ((await child.exited) !== 0) {
    throw new Error(
      "GitHub CLI could not complete setup. Check gh auth status and repository " +
        "administration access.",
    );
  }

  return output;
};
