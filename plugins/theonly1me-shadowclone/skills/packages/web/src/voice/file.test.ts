import { expect, test } from "bun:test";
import { lstat, mkdir, readlink, stat, symlink } from "node:fs/promises";
import path from "node:path";
import { buildFixture } from "@shadowclone/builds/testing";
import { voiceFilePath, voiceFileState, writeVoiceFile } from "./file";

async function home() {
  const fixture = await buildFixture();
  const file = voiceFilePath(fixture.paths);

  return { fixture, file };
}

test("a missing voice file is created with owner-only permissions", async () => {
  const { fixture, file } = await home();

  expect(await writeVoiceFile({ paths: fixture.paths, content: "# My writing voice\n" })).toBe(file);
  expect(await Bun.file(file).text()).toBe("# My writing voice\n");
  expect((await stat(file)).mode & 0o777).toBe(0o600);
});

test("an existing voice file is never overwritten", async () => {
  const { fixture, file } = await home();

  await Bun.write(file, "# Mine\n");

  await expect(writeVoiceFile({ paths: fixture.paths, content: "# New\n" })).rejects.toThrow(
    `${file} already exists, so Shadowclone did not change it`,
  );
  expect(await Bun.file(file).text()).toBe("# Mine\n");
});

test("a linked voice file is never written through, even when the link is broken", async () => {
  const { fixture, file } = await home();
  const target = path.join(path.dirname(file), "elsewhere", "voice.md");

  await mkdir(path.dirname(file), { recursive: true });
  await symlink(target, file);

  expect(await voiceFileState(fixture.paths)).toEqual({ path: file, state: "link", target });
  await expect(writeVoiceFile({ paths: fixture.paths, content: "# New\n" })).rejects.toThrow(`as a link to ${target}`);
  expect((await lstat(file)).isSymbolicLink()).toBeTrue();
  expect(await readlink(file)).toBe(target);
  expect(await Bun.file(target).exists()).toBeFalse();
});
