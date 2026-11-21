import { expect, test } from "bun:test";
import { isOriginBlocked } from "./blockedOrigin";
import { normalizeRemoteRepository, resolveRepository } from "./origin";

const acme = normalizeRemoteRepository("git@github.com:acme/secret-api.git");

function blocked(patterns: readonly string[]): boolean {
  if (!acme) {
    throw new Error("Expected a normalized repository");
  }

  return isOriginBlocked({ repository: acme, patterns });
}

test("matches a wildcard across the host and owner separator", () => {
  expect(blocked(["*acme*"])).toBeTrue();
  expect(blocked(["*"])).toBeTrue();
  expect(blocked(["github.com/*"])).toBeTrue();
  expect(blocked(["*security*"])).toBeFalse();
});

test("matches a repository pattern against the parsed remote", () => {
  expect(blocked(["github.com/acme/secret-*"])).toBeTrue();
  expect(blocked(["*/secret-api"])).toBeTrue();
  expect(blocked(["github.com/acme/public-api"])).toBeFalse();
});

test("blocks a repository cloned into a differently named directory", async () => {
  const repository = await resolveRepository({
    cwd: "/work/innocent-looking-checkout",
    enabled: true,
    readRemote: async () => "git@github.com:acme/secret-api.git",
  });

  expect(
    isOriginBlocked({
      repository,
      patterns: ["github.com/acme/secret-api"],
    }),
  ).toBeTrue();
});

test("does not block an unrelated repository sharing a directory name", async () => {
  const repository = await resolveRepository({
    cwd: "/work/secret-api",
    enabled: true,
    readRemote: async () => "git@github.com:acme/public-api.git",
  });

  expect(
    isOriginBlocked({
      repository,
      patterns: ["github.com/acme/secret-api"],
    }),
  ).toBeFalse();
});

test("cannot match a repository pattern without git metadata consent", async () => {
  const repository = await resolveRepository({
    cwd: "/work/secret-api",
    enabled: false,
  });

  expect(
    isOriginBlocked({
      repository,
      patterns: ["github.com/acme/secret-api"],
    }),
  ).toBeFalse();
});

test("treats every character other than an asterisk as a literal", () => {
  expect(blocked(["!github.com/acme"])).toBeFalse();
  expect(blocked(["github.com/acm?"])).toBeFalse();
  expect(blocked(["github.com/{acme,other}"])).toBeFalse();
  expect(blocked(["githubXcom/acme"])).toBeFalse();
});

test("blocks nothing when the managed policy lists no patterns", () => {
  expect(blocked([])).toBeFalse();
});
