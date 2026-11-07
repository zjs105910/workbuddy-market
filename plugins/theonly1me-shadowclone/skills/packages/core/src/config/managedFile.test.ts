import { expect, test } from "bun:test";
import { mkdtemp, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  managedPathAncestors,
  managedStatsFailure,
  readRootOwnedFile,
  type PathStats,
} from "./managedFile";

const rootDirectory: PathStats = {
  uid: 0,
  mode: 0o755,
  isFile: false,
  isDirectory: true,
  isSymbolicLink: false,
};

const rootFile: PathStats = {
  uid: 0,
  mode: 0o644,
  isFile: true,
  isDirectory: false,
  isSymbolicLink: false,
};

test("a root-owned file under root-owned directories is accepted", () => {
  expect(
    managedStatsFailure({ directories: [rootDirectory], file: rootFile }),
  ).toBeNull();
});

test("a file owned by an ordinary user is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [rootDirectory],
      file: { ...rootFile, uid: 501 },
    }),
  ).toBe("Managed policy must be owned by root");
});

test("a root-owned but group-writable file is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [rootDirectory],
      file: { ...rootFile, mode: 0o664 },
    }),
  ).toBe("Managed policy must not be writable by other users");
});

test("a root-owned but world-writable file is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [rootDirectory],
      file: { ...rootFile, mode: 0o666 },
    }),
  ).toBe("Managed policy must not be writable by other users");
});

test("a symbolic link standing in for the policy is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [rootDirectory],
      file: { ...rootFile, isSymbolicLink: true, isFile: false },
    }),
  ).toBe("Managed policy must not be a symbolic link");
});

test("a policy that is not a regular file is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [rootDirectory],
      file: { ...rootFile, isFile: false },
    }),
  ).toBe("Managed policy must be a regular file");
});

test("a parent directory owned by an ordinary user is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [rootDirectory, { ...rootDirectory, uid: 501 }],
      file: rootFile,
    }),
  ).toBe("Managed policy must sit under root-owned directories");
});

test("a world-writable parent directory is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [{ ...rootDirectory, mode: 0o777 }],
      file: rootFile,
    }),
  ).toBe("Managed policy directories must not be writable by other users");
});

test("a symbolic link anywhere in the parent chain is rejected", () => {
  expect(
    managedStatsFailure({
      directories: [rootDirectory, { ...rootDirectory, isSymbolicLink: true }],
      file: rootFile,
    }),
  ).toBe("Managed policy path must not contain a symbolic link");
});

test("the ancestor chain walks every directory up to the filesystem root", () => {
  expect(managedPathAncestors("/etc/shadowclone/managed.json")).toEqual([
    "/etc/shadowclone",
    "/etc",
    "/",
  ]);
});

test("a policy an ordinary user could write is refused when actually read", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-managed-"),
  );
  const filePath = path.join(directory, "managed.json");

  await writeFile(filePath, JSON.stringify({ enabled: false }));

  await expect(readRootOwnedFile(filePath)).rejects.toThrow(
    "Managed policy must sit under root-owned directories",
  );
});
