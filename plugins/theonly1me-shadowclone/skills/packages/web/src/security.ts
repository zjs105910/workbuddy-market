export function authorizeBrowserRequest(options: {
  readonly request: Request;
  readonly origin: string;
  readonly token: string;
}): boolean {
  const url = new URL(options.request.url);

  if (url.origin !== options.origin) {
    return false;
  }

  const origin = options.request.headers.get("origin");

  if (origin !== null && origin !== options.origin) {
    return false;
  }

  if (options.request.method !== "GET" && origin !== options.origin) {
    return false;
  }

  const authorization = options.request.headers.get("authorization");

  return authorization === `Bearer ${options.token}`;
}

export function browserJson(options: {
  readonly body: unknown;
  readonly status?: number;
}): Response {
  return Response.json(options.body, {
    status: options.status ?? 200,
    headers: {
      "Cache-Control": "no-store",
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    },
  });
}
