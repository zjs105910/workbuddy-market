import { expect, test } from "bun:test";
import { appManifest, createManifestCallback } from "./app";
import { syntheticApp } from "./fixtures";

const origin = "http://127.0.0.1:12345";

test("the manifest registers a personal App without an external webhook service", () => {
  const manifest = appManifest({ name: "sample-clone", origin });

  expect(manifest.name).toBe("sample-clone");
  expect(manifest.public).toBeFalse();
  expect(manifest.hook_attributes.active).toBeFalse();
  expect(manifest.default_permissions.workflows).toBe("write");
  expect(manifest.redirect_url).toBe(`${origin}/api/bot/callback`);
});

test(
  "manifest conversion checks state, host, owner, and single use without " + "echoing secrets",
  async () => {
    const app = syntheticApp();
    const accepted: number[] = [];
    const callback = createManifestCallback({
      origin: () => origin,
      owner: "sample",
      api: async () => app,
      onApp: async (created) => {
        accepted.push(created.id);
      },
    });
    const callbackUrl = `${origin}/api/bot/callback?state=${callback.state}&code=${"synthetic".repeat(4)}`;

    expect(
      (await callback.handle(new Request(callbackUrl.replace(callback.state, "wrong")))).status,
    ).toBe(403);
    expect(
      (await callback.handle(new Request(callbackUrl.replace(origin, "http://example.invalid"))))
        .status,
    ).toBe(403);

    const response = await callback.handle(new Request(callbackUrl));

    expect(response.status).toBe(303);
    expect(response.headers.get("referrer-policy")).toBe("no-referrer");
    expect(await response.text()).not.toContain(app.pem);
    expect(accepted).toEqual([app.id]);
    expect((await callback.handle(new Request(callbackUrl))).status).toBe(403);
  },
);

test("a foreign App owner cannot complete registration", async () => {
  const app = syntheticApp();
  const callback = createManifestCallback({
    origin: () => origin,
    owner: "sample",
    api: async () => ({ ...app, owner: { login: "outside" } }),
    onApp: async () => {
      throw new Error("A foreign registration must not be accepted.");
    },
  });
  const response = await callback.handle(
    new Request(`${origin}/api/bot/callback?state=${callback.state}&code=${"synthetic".repeat(4)}`),
  );

  expect(response.status).toBe(400);
  expect(await response.text()).not.toContain(app.pem);
});
