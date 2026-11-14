import { mkdtemp, readFile, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import type { DeliveryFile } from "../deliveryFiles";
import { ghApiData, type GhApiCall } from "./ghApi";

export const skillsRepositoryName = "shadowclone-skills";

const repositorySchema = z.object({
  full_name: z.string(),
  private: z.boolean(),
  default_branch: z.string(),
});
const shaSchema = z.object({ sha: z.string().regex(/^[a-f0-9]{40}$/) });
const keysSchema = z.array(z.object({ id: z.number().int().positive(), title: z.string() }));

export async function ensureSkillsRepository(options: {
  readonly call: GhApiCall;
  readonly owner: string;
}): Promise<string> {
  const name = `${options.owner}/${skillsRepositoryName}`;
  const existing = await options.call({ route: `repos/${name}` });

  if (existing.status === 404) {
    await ghApiData({
      call: options.call,
      method: "POST",
      route: "user/repos",
      body: {
        name: skillsRepositoryName,
        private: true,
        auto_init: true,
        description: "Engineering skills for my Shadowclone cloud bot",
      },
    });

    return name;
  }

  const repository = repositorySchema.parse(
    await ghApiData({ call: options.call, route: `repos/${name}` }),
  );

  if (!repository.private) {
    throw new Error(`${name} is public. Make it private before setup pushes your skills to it.`);
  }

  return repository.full_name;
}

export async function pushSkills(options: {
  readonly call: GhApiCall;
  readonly repository: string;
  readonly files: readonly DeliveryFile[];
}): Promise<"pushed" | "unchanged"> {
  const { call, repository } = options;
  const base = `repos/${repository}`;
  const branch = repositorySchema.parse(await ghApiData({ call, route: base })).default_branch;
  const head = z
    .object({ object: shaSchema })
    .parse(await ghApiData({ call, route: `${base}/git/ref/heads/${branch}` })).object.sha;
  const current = z
    .object({ tree: shaSchema })
    .parse(await ghApiData({ call, route: `${base}/git/commits/${head}` })).tree.sha;
  const entries = [];

  for (const file of options.files) {
    const blob = shaSchema.parse(
      await ghApiData({
        call,
        method: "POST",
        route: `${base}/git/blobs`,
        body: { content: file.content, encoding: "base64" },
      }),
    );

    entries.push({
      path: file.path,
      mode: (file.mode & 0o111) === 0 ? "100644" : "100755",
      type: "blob",
      sha: blob.sha,
    });
  }

  const tree = shaSchema.parse(
    await ghApiData({ call, method: "POST", route: `${base}/git/trees`, body: { tree: entries } }),
  ).sha;

  if (tree === current) {
    return "unchanged";
  }

  const commit = shaSchema.parse(
    await ghApiData({
      call,
      method: "POST",
      route: `${base}/git/commits`,
      body: { message: "chore: update the reviewed skills", tree, parents: [head] },
    }),
  ).sha;

  await ghApiData({
    call,
    method: "PATCH",
    route: `${base}/git/refs/heads/${branch}`,
    body: { sha: commit },
  });

  return "pushed";
}

export async function addSkillsDeployKey(options: {
  readonly call: GhApiCall;
  readonly skillsRepository: string;
  readonly target: string;
}): Promise<string> {
  const { call } = options;
  const title = `shadowclone ${options.target}`;
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-key-"));
  const keyPath = path.join(directory, "key");

  try {
    const generated = Bun.spawn(
      ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", title, "-f", keyPath],
      { stdout: "ignore", stderr: "ignore" },
    );

    if ((await generated.exited) !== 0) {
      throw new Error("ssh-keygen could not create the deploy key.");
    }

    const keys = keysSchema.parse(
      await ghApiData({ call, route: `repos/${options.skillsRepository}/keys?per_page=100` }),
    );

    for (const key of keys.filter((candidate) => candidate.title === title)) {
      await ghApiData({
        call,
        method: "DELETE",
        route: `repos/${options.skillsRepository}/keys/${key.id}`,
      });
    }

    await ghApiData({
      call,
      method: "POST",
      route: `repos/${options.skillsRepository}/keys`,
      body: { title, key: (await readFile(`${keyPath}.pub`, "utf8")).trim(), read_only: true },
    });

    return await readFile(keyPath, "utf8");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
