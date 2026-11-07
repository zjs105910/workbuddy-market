import { expect, test } from "bun:test";
import os from "node:os";
import path from "node:path";
import {
  normalizeRemoteOrigin,
  normalizeRemoteRepository,
  readGitRemote,
} from "./remote";

test("a missing working directory has no Git remote", async () => {
  const missingDirectory = path.join(
    os.tmpdir(),
    `shadowclone-missing-${crypto.randomUUID()}`,
  );

  expect(await readGitRemote(missingDirectory)).toBeNull();
});

test("nested namespaces stay distinct owners", () => {
  const first = normalizeRemoteOrigin("https://gitlab.com/group/alpha/service");
  const second = normalizeRemoteOrigin("https://gitlab.com/group/beta/service");

  expect(first?.id).toBe("gitlab.com/group/alpha");
  expect(second?.id).toBe("gitlab.com/group/beta");
  expect(first?.id).not.toBe(second?.id);
});

test("nested namespaces stay distinct repositories", () => {
  const first = normalizeRemoteRepository(
    "https://gitlab.com/group/alpha/service.git",
  );
  const second = normalizeRemoteRepository(
    "https://gitlab.com/group/beta/service.git",
  );

  expect(first?.id).toBe("gitlab.com/group/alpha/service");
  expect(second?.id).toBe("gitlab.com/group/beta/service");
  expect(first?.profileFileName).not.toBe(second?.profileFileName);
});

test("the last path segment is the repository, not the second", () => {
  expect(
    normalizeRemoteRepository("https://gitlab.com/group/alpha/service.git")
      ?.name,
  ).toBe("service");
});

test("a port distinguishes two hosts at the same name", () => {
  const standard = normalizeRemoteOrigin("https://git.example.com/team/app");
  const alternate = normalizeRemoteOrigin(
    "ssh://git@git.example.com:2222/team/app",
  );

  expect(standard?.id).toBe("git.example.com/team");
  expect(alternate?.id).toBe("git.example.com:2222/team");
  expect(standard?.id).not.toBe(alternate?.id);
  expect(alternate?.directoryName).toBe(
    "git.example.com--2222--team--a1acd481aa078b93",
  );
});

test("the url and scp forms of one nested remote agree", () => {
  const url = normalizeRemoteRepository(
    "https://gitlab.com/group/alpha/service.git",
  );
  const secureShell = normalizeRemoteRepository(
    "git@gitlab.com:group/alpha/service.git",
  );

  expect(secureShell?.id).toBe(url?.id);
  expect(secureShell?.origin.id).toBe(url?.origin.id);
  expect(secureShell?.profileFileName).toBe(url?.profileFileName);
});

test("a plain github remote keeps its existing identity", () => {
  expect(
    normalizeRemoteOrigin("https://private-token@github.com/Acme/platform.git"),
  ).toEqual({
    id: "github.com/acme",
    directoryName: "github.com--acme--936913df4a5c268b",
    promotable: true,
  });
  expect(
    normalizeRemoteRepository("git@github.com:acme/secret-api.git")?.id,
  ).toBe("github.com/acme/secret-api");
});

test("a remote with no owner segment is refused", () => {
  expect(normalizeRemoteOrigin("https://github.com/repo")).toBeNull();
  expect(normalizeRemoteOrigin("git@github.com:repo.git")).toBeNull();
});

test("a value that is not a remote is refused", () => {
  expect(normalizeRemoteOrigin("not a remote")).toBeNull();
  expect(normalizeRemoteOrigin("")).toBeNull();
});

test("a repository file name drops dots, dashes, and underscores at both ends", () => {
  expect(
    normalizeRemoteRepository("https://github.com/acme/-_.My-Repo._-")?.profileFileName,
  ).toMatch(/^my-repo--[0-9a-f]{16}$/);
  expect(
    normalizeRemoteRepository("https://github.com/acme/._-")?.profileFileName,
  ).toMatch(/^repository--[0-9a-f]{16}$/);
});

test("a repository name with a long run of dashes gets its file name in linear time", () => {
  const started = performance.now();
  const repository = normalizeRemoteRepository(
    `https://github.com/acme/a${"-".repeat(100_000)}b`,
  );

  expect(performance.now() - started).toBeLessThan(1_000);
  expect(repository?.profileFileName).toStartWith(`a${"-".repeat(63)}--`);
});
