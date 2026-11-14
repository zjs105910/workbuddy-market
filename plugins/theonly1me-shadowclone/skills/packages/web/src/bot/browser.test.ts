import { expect, test } from "bun:test";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { readEnvironment, writeEnvironment } from "@shadowclone/environment";
import { writeMaintenanceState } from "@shadowclone/skills";
import { createBotBrowser } from "./browser";
import { guidanceFixture, setupRepository, syntheticApp } from "@shadowclone/cloud/testing";
import { setupPreviewSchema, manifestViewSchema } from "@shadowclone/cloud";
import { createBrowserHandler } from "../handler";

const origin = "http://127.0.0.1:12345";

function setupRequest(options: { readonly path: string; readonly body?: unknown }) {
  return new Request(`${origin}${options.path}`, {
    method: options.body === undefined ? "GET" : "POST",
    headers: {
      Origin: origin,
      Authorization: "Bearer synthetic-session",
      "Content-Type": "application/json",
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
}

test("browser setup previews exact scoped guidance and registers the reviewed App name", async () => {
  const fixture = await guidanceFixture();
  const app = syntheticApp();
  const bot = createBotBrowser({
    ...fixture,
    origin: () => origin,
    command: async ({ arguments: arguments_ }) =>
      JSON.stringify(arguments_[1] === "user" ? { login: "sample" } : setupRepository),
    api: async () => app,
  });

  try {
    const response = await bot(
      setupRequest({
        path: "/api/bot/preview",
        body: { repository: "sample/project", name: "sample-clone", skills: ["shadowclone-work"] },
      }),
    );
    const preview = setupPreviewSchema.parse(await response.json());

    expect(preview.repositoryId).toBe(10);
    expect(preview.files.some((file) => file.path === "native.md")).toBeTrue();
    expect(JSON.stringify(preview)).not.toContain(fixture.root);

    const view = manifestViewSchema.parse(
      await (
        await bot(setupRequest({ path: "/api/bot/manifest", body: { previewId: preview.id } }))
      ).json(),
    );
    const manifest: unknown = JSON.parse(view.manifest);

    expect(manifest).toMatchObject({ name: "sample-clone", public: false });
    expect(view.action).toStartWith("https://github.com/settings/apps/new?state=");
  } finally {
    await fixture.cleanup();
  }
});

test("the editor rejects unauthenticated setup writes and a stale preview", async () => {
  const fixture = await guidanceFixture();
  let calls = 0;
  const botHandler = createBotBrowser({
    ...fixture,
    origin: () => origin,
    command: async () => {
      calls += 1;
      return "{}";
    },
  });
  const handler = createBrowserHandler({
    ...fixture,
    token: "synthetic-session",
    origin: () => origin,
    botHandler,
  });

  try {
    const missing = setupRequest({ path: "/api/bot/preview", body: {} });

    missing.headers.delete("Authorization");
    expect((await handler(missing)).status).toBe(403);
    expect(calls).toBe(0);

    const token = `sk-ant-oat01-${"synthetic".repeat(10)}`;
    const stale = await handler(
      setupRequest({ path: "/api/bot/activate", body: { previewId: crypto.randomUUID(), token } }),
    );

    expect(stale.status).toBe(400);
    expect(await stale.text()).not.toContain(token);
    expect(calls).toBe(0);
  } finally {
    await fixture.cleanup();
  }
});

test("an organization repository registers its private App under that organization", async () => {
  const fixture = await guidanceFixture();
  const bot = createBotBrowser({
    ...fixture,
    readRemote: async () => "https://github.com/sample-org/project.git",
    origin: () => origin,
    command: async ({ arguments: arguments_ }) =>
      JSON.stringify(
        arguments_[1] === "user"
          ? { login: "sample" }
          : {
              ...setupRepository,
              full_name: "sample-org/project",
              owner: { login: "sample-org", type: "Organization" },
            },
      ),
  });

  try {
    const preview = setupPreviewSchema.parse(
      await (
        await bot(
          setupRequest({
            path: "/api/bot/preview",
            body: {
              repository: "sample-org/project",
              name: "sample-clone",
              skills: ["shadowclone-work"],
            },
          }),
        )
      ).json(),
    );
    const view = manifestViewSchema.parse(
      await (
        await bot(
          setupRequest({
            path: "/api/bot/manifest",
            body: { previewId: preview.id },
          }),
        )
      ).json(),
    );

    expect(preview.appOwner).toBe("sample-org");
    expect(preview.owner).toBe("sample");
    expect(view.action).toStartWith(
      "https://github.com/organizations/sample-org/settings/apps/new?state=",
    );
  } finally {
    await fixture.cleanup();
  }
});

test("setup starts from the personal build and leaves unequipped plugin skills out", async () => {
  const fixture = await guidanceFixture();
  const home = path.dirname(fixture.paths.shadowcloneDirectory);
  const plugins = path.join(home, ".claude/plugins/cache");
  const state = await readEnvironment(fixture.paths);

  if (!state) throw new Error("The fixture environment is missing");

  await writeConfig({
    config: { ...defaultConfig, sources: { ...defaultConfig.sources, "skill-library": true } },
    configPath: fixture.paths.configFile,
  });
  await Bun.write(
    path.join(plugins, "vendor/skills/vendor-sdk/SKILL.md"),
    "---\nname: vendor-sdk\ndescription: Use the vendor SDK.\n---\n\nCall the SDK.\n",
  );
  await writeMaintenanceState({
    paths: fixture.paths,
    state: {
      version: 1,
      roots: [
        {
          id: "0".repeat(64),
          directory: plugins,
          cwd: home,
          scope: "global",
          owner: "third-party",
          destination: path.join(home, ".claude/skills"),
          enabled: true,
        },
      ],
      tracked: [],
      assessed: {},
      findings: {},
      rejected: {},
    },
  });
  await writeEnvironment({
    paths: fixture.paths,
    state: {
      ...state,
      builds: [
        {
          id: "global",
          scope: "global",
          directory: home,
          choices: { "careful-review": true },
          edits: {},
          custom: [],
        },
      ],
      artifacts: [
        ...state.artifacts,
        {
          filePath: path.join(home, ".agents/skills/careful-review/SKILL.md"),
          fingerprint: "synthetic",
          original: null,
          kind: "skill",
          scope: "global",
          name: "careful-review",
          description: "Review a change before handoff.",
          learningKeys: [],
          buildId: "global",
          buildEntryId: "careful-review",
        },
      ],
    },
  });

  const bot = createBotBrowser({ ...fixture, origin: () => origin });

  try {
    expect(await (await bot(setupRequest({ path: "/api/bot/state" }))).json()).toMatchObject({
      skills: ["careful-review", "shadowclone-work"],
    });
  } finally {
    await fixture.cleanup();
  }
});

test("a failed preview names its reason", async () => {
  const fixture = await guidanceFixture();
  const preview = async (skills: readonly string[]) => {
    const bot = createBotBrowser({
      ...fixture,
      origin: () => origin,
      command: async ({ arguments: arguments_ }) =>
        JSON.stringify(arguments_[1] === "user" ? { login: "sample" } : setupRepository),
    });
    const response = await bot(
      setupRequest({
        path: "/api/bot/preview",
        body: { repository: "sample/project", name: "sample-clone", skills },
      }),
    );

    return { status: response.status, body: await response.json() };
  };

  try {
    expect(await preview(["shadowclone-work", "missing-skill"])).toEqual({
      status: 400,
      body: { error: "A selected skill is not available in this repository scope." },
    });
    expect(await preview([])).toEqual({
      status: 400,
      body: {
        error: "Enter the repository as owner/repository, a clone name, and 1 to 40 skill names.",
      },
    });
  } finally {
    await fixture.cleanup();
  }
});
