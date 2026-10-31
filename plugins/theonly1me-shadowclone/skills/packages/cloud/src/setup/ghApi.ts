import type { GithubApi } from "./github";

export type GhResponse = { readonly status: number; readonly data: unknown };

export type GhApiCall = (options: {
  readonly method?: string;
  readonly route: string;
  readonly body?: unknown;
}) => Promise<GhResponse>;

export const ghApiCall: GhApiCall = async (options) => {
  const executable = Bun.which("gh");

  if (!executable) {
    throw new Error("Install GitHub CLI and run gh auth login before setup.");
  }

  const child = Bun.spawn(
    [
      executable,
      "api",
      "--include",
      "--method",
      options.method ?? "GET",
      options.route,
      ...(options.body === undefined ? [] : ["--input", "-"]),
    ],
    {
      stdin: options.body === undefined ? "ignore" : new Blob([JSON.stringify(options.body)]),
      stdout: "pipe",
      stderr: "ignore",
    },
  );
  const output = await new Response(child.stdout).text();

  await child.exited;

  const separator = /\r?\n\r?\n/.exec(output);
  const head = separator === null ? output : output.slice(0, separator.index);
  const body = separator === null ? "" : output.slice(separator.index + separator[0].length).trim();
  const status = Number(/^HTTP\/[\d.]+ (\d{3})/.exec(head)?.[1] ?? 0);

  if (status === 0) {
    throw new Error("GitHub CLI could not reach GitHub. Check gh auth status.");
  }

  return { status, data: body.length > 0 ? JSON.parse(body) : null };
};

export async function ghApiData(options: {
  readonly call: GhApiCall;
  readonly method?: string;
  readonly route: string;
  readonly body?: unknown;
}): Promise<unknown> {
  const { call, ...request } = options;
  const response = await call(request);

  if (response.status >= 300) {
    throw new Error(
      `GitHub refused ${request.method ?? "GET"} ${request.route} (${response.status}). Check gh auth status and repository access.`,
    );
  }

  return response.data;
}

export function githubApiThroughGh(call: GhApiCall): GithubApi {
  return async (options) => {
    const [method = "GET", pathname = ""] = options.route.split(" ");

    return ghApiData({ call, method, route: pathname.replace(/^\//, ""), body: options.body });
  };
}
