import path from "node:path";

export function browserAssetRoutes(options: {
  readonly page: Bun.HTMLBundle;
  readonly directory: string;
}): Record<string, Bun.HTMLBundle | Response> {
  const { page, directory } = options;

  if (!page.files) {
    return { "/": page };
  }

  const routes: Record<string, Response> = {};

  for (const file of page.files) {
    const route =
      file.path === page.index
        ? "/"
        : new URL(file.path.replaceAll(path.sep, "/"), "http://localhost/")
            .pathname;

    routes[route] = new Response(Bun.file(path.resolve(directory, file.path)), {
      headers: {
        ...file.headers,
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
      },
    });
  }

  return routes;
}
