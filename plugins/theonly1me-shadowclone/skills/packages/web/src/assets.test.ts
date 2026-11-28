import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { browserAssetRoutes } from "./assets";

test("packaged routes resolve beside the installed bundle and keep public asset URLs", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-assets-"),
  );

  try {
    const html = '<link rel="stylesheet" href="/web/styles.css">';
    const css = "body { color: white; }";

    await Bun.write(path.join(directory, "pages/index.html"), html);
    await Bun.write(path.join(directory, "web/styles.css"), css);

    const routes = browserAssetRoutes({
      directory,
      page: {
        index: "pages/index.html",
        files: [
          {
            path: "pages/index.html",
            loader: "html",
            isEntry: true,
            headers: { etag: "page", "content-type": "text/html" },
          },
          {
            path: "./web/styles.css",
            loader: "css",
            isEntry: true,
            headers: { etag: "styles", "content-type": "text/css" },
          },
        ],
      },
    });

    const page = routes["/"];
    const stylesheet = routes["/web/styles.css"];

    expect(page).toBeInstanceOf(Response);
    expect(stylesheet).toBeInstanceOf(Response);

    if (!(page instanceof Response) || !(stylesheet instanceof Response)) {
      throw new Error("Expected static packaged responses");
    }

    expect(await page.text()).toBe(html);
    expect(await stylesheet.text()).toBe(css);
    expect(stylesheet.headers.get("content-type")).toBe("text/css");
    expect(Object.keys(routes)).toEqual(["/", "/web/styles.css"]);
    expect(routes["/../config.toml"]).toBeUndefined();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("source development keeps Bun's HTML bundling route", () => {
  const page = { index: "./client/index.html" };

  expect(browserAssetRoutes({ page, directory: "/synthetic" })).toEqual({
    "/": page,
  });
});
