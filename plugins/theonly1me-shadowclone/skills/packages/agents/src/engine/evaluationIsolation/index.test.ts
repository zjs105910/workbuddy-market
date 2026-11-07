import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { canonicalPath } from "@shadowclone/core";
import { evaluationCommand } from "./index";

async function linkedDirectory(): Promise<{
  readonly root: string;
  readonly target: string;
  readonly link: string;
}> {
  const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-isolation-"));
  const target = path.join(root, "control");
  const link = path.join(root, "link");

  await mkdir(target);
  await symlink(target, link);

  return { root, target, link };
}

test("denies the resolved path so a symbolic link cannot escape the macOS sandbox", async () => {
  const { root, target, link } = await linkedDirectory();

  try {
    const command = evaluationCommand({
      arguments: ["claude"],
      run: {
        prompt: "",
        cwd: root,
        execution: { purpose: "evaluation", blockedPaths: [link] },
      },
      platform: "darwin",
    });

    const profile = command[2] ?? "";

    expect(profile).toContain(
      `(subpath ${JSON.stringify(canonicalPath(target))})`,
    );
    expect(profile).not.toContain(`(subpath ${JSON.stringify(link)})`);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("covers a temporary directory reached through the platform tmpdir symlink", async () => {
  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-control-"),
  );

  try {
    const command = evaluationCommand({
      arguments: ["claude"],
      run: {
        prompt: "",
        cwd: directory,
        execution: { purpose: "evaluation", blockedPaths: [directory] },
      },
      platform: "darwin",
    });

    expect(command[2]).toContain(
      `(subpath ${JSON.stringify(canonicalPath(directory))})`,
    );
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("mounts the resolved path over a symbolic link on Linux", async () => {
  const { root, target, link } = await linkedDirectory();

  try {
    const command = evaluationCommand({
      arguments: ["codex"],
      run: {
        prompt: "",
        cwd: root,
        execution: { purpose: "evaluation", blockedPaths: [link] },
      },
      platform: "linux",
    });

    expect(command).toContain(canonicalPath(target));
    expect(command).not.toContain(link);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("wraps evaluation even when no additional paths are blocked", () => {
  expect(
    evaluationCommand({
      arguments: ["claude", "-p"],
      run: { prompt: "", cwd: "/tmp", execution: { purpose: "evaluation" } },
      platform: "darwin",
    }),
  ).toContain("sandbox-exec");
});

test("refuses to run an isolated evaluation on an unsupported platform", () => {
  expect(() =>
    evaluationCommand({
      arguments: ["claude"],
      run: {
        prompt: "",
        cwd: "/tmp",
        execution: {
          purpose: "evaluation",
          blockedPaths: ["/tmp/control"],
        },
      },
      platform: "win32",
    }),
  ).toThrow("macOS or Linux");
});
