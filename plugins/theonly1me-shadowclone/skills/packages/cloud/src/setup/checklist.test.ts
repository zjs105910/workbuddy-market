import { expect, test } from "bun:test";
import { fixtureAccountClone, fixtureClone } from "../fixtures";
import { readCloudChecklist } from "./checklist";
import { ghApiFixture } from "./fixtures";

function repositoryState(options: {
  readonly secrets: readonly string[];
  readonly merged: boolean;
  readonly collaborator: boolean;
}) {
  return ghApiFixture({
    "GET repos/sample/project/environments/shadowclone": { status: 200, data: { id: 77 } },
    "GET repos/sample/project/environments/shadowclone/secrets?per_page=100": {
      status: 200,
      data: { secrets: options.secrets.map((name) => ({ name })) },
    },
    "GET repos/sample/project/contents/.github/workflows/shadowclone-relay.yml?ref=main": {
      status: options.merged ? 200 : 404,
      data: null,
    },
    "GET repos/sample/project/collaborators/sample-shadow": {
      status: options.collaborator ? 204 : 404,
      data: null,
    },
    "GET repos/sample/project/invitations?per_page=100": {
      status: 200,
      data: [{ invitee: { login: "sample-shadow" } }],
    },
  });
}

test("a fresh machine account setup lists the tokens to add on GitHub, with the token and environment pages", async () => {
  const { call } = repositoryState({
    secrets: ["SHADOWCLONE_SKILLS_KEY"],
    merged: false,
    collaborator: false,
  });
  const checklist = await readCloudChecklist({
    call,
    clone: fixtureAccountClone,
    pullUrl: "https://github.com/sample/project/pull/5",
  });

  expect(checklist.map((item) => [item.key, item.done])).toEqual([
    ["bot-token", false],
    ["model-token", false],
    ["skills", true],
    ["workflows", false],
    ["invitation", false],
  ]);
  expect(checklist[0]?.links.map((link) => link.url)).toEqual([
    "https://github.com/settings/tokens/new?scopes=repo&description=shadowclone+sample%2Fproject",
    "https://github.com/sample/project/settings/environments/77/edit",
  ]);
  expect(checklist[4]?.action).toContain("mention @sample-shadow once");
});

test("the checklist reads secret names only, and marks a finished setup done", async () => {
  const { call, calls } = repositoryState({
    secrets: ["SHADOWCLONE_BOT_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN", "SHADOWCLONE_SKILLS_KEY"],
    merged: true,
    collaborator: true,
  });
  const checklist = await readCloudChecklist({ call, clone: fixtureAccountClone, pullUrl: null });

  expect(checklist.every((item) => item.done)).toBeTrue();
  expect(calls.every((request) => request.method === "GET")).toBeTrue();
});

test("an App setup checks the uploaded App key and has no invitation step", async () => {
  const { call } = repositoryState({
    secrets: ["SHADOWCLONE_APP_PRIVATE_KEY"],
    merged: true,
    collaborator: false,
  });
  const checklist = await readCloudChecklist({ call, clone: fixtureClone, pullUrl: null });

  expect(checklist.map((item) => [item.key, item.done])).toEqual([
    ["app-key", true],
    ["model-token", false],
    ["skills", false],
    ["workflows", true],
  ]);
});
