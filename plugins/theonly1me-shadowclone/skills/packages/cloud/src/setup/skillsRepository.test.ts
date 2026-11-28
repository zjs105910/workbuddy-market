import { expect, test } from "bun:test";
import { ghApiFixture } from "./fixtures";
import { addSkillsDeployKey, ensureSkillsRepository, pushSkills } from "./skillsRepository";

const sha = (letter: string) => letter.repeat(40);
const files = [
  { path: "native.md", content: Buffer.from("Use full names.").toString("base64"), mode: 0o600 },
];

function pushFixture(options: { readonly newTree: string }) {
  return ghApiFixture({
    "GET repos/sample/shadowclone-skills": {
      status: 200,
      data: { full_name: "sample/shadowclone-skills", private: true, default_branch: "main" },
    },
    "GET repos/sample/shadowclone-skills/git/ref/heads/main": {
      status: 200,
      data: { object: { sha: sha("a") } },
    },
    [`GET repos/sample/shadowclone-skills/git/commits/${sha("a")}`]: {
      status: 200,
      data: { tree: { sha: sha("b") } },
    },
    "POST repos/sample/shadowclone-skills/git/blobs": { status: 201, data: { sha: sha("c") } },
    "POST repos/sample/shadowclone-skills/git/trees": {
      status: 201,
      data: { sha: options.newTree },
    },
    "POST repos/sample/shadowclone-skills/git/commits": { status: 201, data: { sha: sha("d") } },
    "PATCH repos/sample/shadowclone-skills/git/refs/heads/main": { status: 200, data: {} },
  });
}

test("setup creates the skills repository as private when it is missing", async () => {
  const { call, calls } = ghApiFixture({ "POST user/repos": { status: 201, data: {} } });

  expect(await ensureSkillsRepository({ call, owner: "sample" })).toBe("sample/shadowclone-skills");
  expect(calls.at(-1)?.body).toMatchObject({ name: "shadowclone-skills", private: true });
});

test("setup refuses to push skills to a public repository", async () => {
  const { call } = ghApiFixture({
    "GET repos/sample/shadowclone-skills": {
      status: 200,
      data: { full_name: "sample/shadowclone-skills", private: false, default_branch: "main" },
    },
  });

  await expect(ensureSkillsRepository({ call, owner: "sample" })).rejects.toThrow("public");
});

test("pushing the same skills again changes nothing, and new skills move the branch", async () => {
  const same = pushFixture({ newTree: sha("b") });

  expect(
    await pushSkills({ call: same.call, repository: "sample/shadowclone-skills", files }),
  ).toBe("unchanged");
  expect(same.calls.some((request) => request.method === "PATCH")).toBeFalse();

  const changed = pushFixture({ newTree: sha("e") });

  expect(
    await pushSkills({ call: changed.call, repository: "sample/shadowclone-skills", files }),
  ).toBe("pushed");
  expect(changed.calls.at(-1)).toMatchObject({ method: "PATCH", body: { sha: sha("d") } });
});

test("a new deploy key replaces the earlier key for the same target and is read-only", async () => {
  const { call, calls } = ghApiFixture({
    "GET repos/sample/shadowclone-skills/keys?per_page=100": {
      status: 200,
      data: [
        { id: 3, title: "shadowclone sample/project" },
        { id: 4, title: "shadowclone sample/other" },
      ],
    },
    "DELETE repos/sample/shadowclone-skills/keys/3": { status: 204, data: null },
    "POST repos/sample/shadowclone-skills/keys": { status: 201, data: {} },
  });
  const privateKey = await addSkillsDeployKey({
    call,
    skillsRepository: "sample/shadowclone-skills",
    target: "sample/project",
  });

  expect(privateKey).toContain("OPENSSH PRIVATE KEY");
  expect(
    calls.filter((request) => request.method === "DELETE").map((request) => request.route),
  ).toEqual(["repos/sample/shadowclone-skills/keys/3"]);
  expect(calls.at(-1)?.body).toMatchObject({
    title: "shadowclone sample/project",
    read_only: true,
  });
  expect(JSON.stringify(calls.at(-1)?.body)).toContain("ssh-ed25519");
});
