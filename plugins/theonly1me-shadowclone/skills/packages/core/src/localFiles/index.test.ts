import { expect, test } from "bun:test";
import { mkdtemp, realpath, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { assertRegularDestination, UnsafeDestinationError } from "./index";

test("a symbolic link destination reports the link that blocks the write", async () => {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "local-files-")));

  try {
    const target = path.join(directory, "shared.md");
    const link = path.join(directory, "AGENTS.md");

    await writeFile(target, "shared");
    await symlink(target, link);

    const failure = (() => {
      try {
        assertRegularDestination(link);
      } catch (error) {
        return error;
      }

      return null;
    })();

    expect(failure).toBeInstanceOf(UnsafeDestinationError);
    expect(failure).toMatchObject({
      message: `Destination must be a regular file without symbolic links: ${link} (a link to ${target})`,
      path: link,
      target,
    });
    expect(() => assertRegularDestination(target)).not.toThrow();
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
