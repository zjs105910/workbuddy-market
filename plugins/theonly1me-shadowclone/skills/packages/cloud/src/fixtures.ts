import path from "node:path";
import os from "node:os";
import { mkdtemp, mkdir, rm } from "node:fs/promises";
import { canonicalPath, createProjectPaths } from "@shadowclone/core";
import { emptyEnvironment, writeEnvironment } from "@shadowclone/environment";
import type { Clone, EventContext, GithubRequest } from "./types";

export const fixtureClone: Clone = {
  repositoryId: 10,
  repository: "sample/project",
  defaultBranch: "main",
  owner: "sample",
  identity: { kind: "app", appId: 20 },
  botId: 30,
  botLogin: "sample-clone[bot]",
  skillsRepository: "sample/shadowclone-skills",
  requesters: ["sample"],
  reviewerBots: ["reviewer[bot]"],
  maximumRuns: 10,
  reviewModel: "claude-opus-5-5",
  reviewNetwork: true,
  engine: "claude",
  codexAuth: "api-key",
};

export const fixtureAccountClone: Clone = {
  ...fixtureClone,
  identity: { kind: "account" },
  botId: 31,
  botLogin: "sample-shadow",
};

export function eventContext(
  options: {
    readonly event?: string;
    readonly actor?: string;
    readonly payload?: Record<string, unknown>;
  } = {},
): EventContext {
  return {
    eventName: options.event ?? "issues",
    actor: options.actor ?? "sample",
    runId: 123,
    repo: { owner: "sample", repo: "project" },
    payload: {
      repository: { id: fixtureClone.repositoryId },
      issue: { number: 1 },
      action: "opened",
      sender: { type: "User" },
      ...options.payload,
    },
  };
}

export function githubFixture(routes: Readonly<Record<string, unknown>>) {
  const calls: { route: string; parameters?: Record<string, unknown> }[] = [];
  const request: GithubRequest = async (route, parameters) => {
    calls.push({ route, parameters });

    if (!(route in routes)) {
      throw new Error(`Unexpected synthetic GitHub route: ${route}`);
    }

    return { data: routes[route] };
  };

  return { request, calls };
}

export const fixtureIssue = { number: 1, state: "open", user: { login: "sample" }, labels: [] };
export const fixturePull = {
  number: 2,
  state: "open",
  user: { id: fixtureClone.botId },
  head: {
    ref: "shadowclone/issue-1",
    sha: "a".repeat(40),
    repo: { id: fixtureClone.repositoryId },
  },
  labels: [],
};

export async function guidanceFixture() {
  const root = canonicalPath(await mkdtemp(path.join(os.tmpdir(), "synthetic-cloud-")));
  const home = path.join(root, "home");
  const cwd = path.join(root, "repository");
  const paths = {
    ...createProjectPaths({ homeDirectory: home, platform: "linux" }),
    managedConfigFile: null,
  };
  const directory = path.join(home, ".agents", "skills", "shadowclone-work");
  const filePath = path.join(directory, "SKILL.md");

  await mkdir(cwd, { recursive: true });
  await Bun.write(
    filePath,
    "---\nname: shadowclone-work\ndescription: Work on a requested issue.\n---\n\nUse " +
      "full names.\n",
  );
  await writeEnvironment({
    paths,
    state: {
      ...emptyEnvironment,
      phase: "active",
      baselineDirectory: home,
      artifacts: [
        {
          filePath,
          fingerprint: "synthetic",
          original: null,
          kind: "skill",
          scope: "global",
          name: "shadowclone-work",
          description: "Work on an issue.",
          learningKeys: [],
        },
      ],
    },
  });

  return {
    root,
    cwd,
    paths,
    directory,
    filePath,
    readRemote: async () => "https://github.com/sample/project.git",
    cleanup: () => rm(root, { recursive: true, force: true }),
  };
}
