import { mkdir } from "node:fs/promises";
import path from "node:path";
import { runProcess } from "@shadowclone/core";
import type { NativeFile } from "./schema";

export function validateNativeFile(file: NativeFile): void {
  const allowed = file.root === "home"
    ? /^(?:\.claude\/CLAUDE\.md|\.codex\/AGENTS(?:\.override)?\.md|\.(?:claude|agents|codex)\/skills\/.+)$/
    : /^(?:AGENTS(?:\.override)?\.md|CLAUDE\.md|\.(?:claude|agents)\/skills\/.+|\.claude\/rules\/.+\.md)$/;

  if (!allowed.test(file.path)) {
    throw new Error("Native guidance contains a non-guidance destination");
  }
}

export async function copyWorkspace(options: { source: string; target: string }): Promise<void> {
  await mkdir(options.target, { recursive: true, mode: 0o700 });
  const source = `${options.source}${path.sep}.`;
  const result = await runProcess({
    arguments: process.platform === "darwin"
      ? ["cp", "-Rc", source, options.target]
      : ["cp", "-R", "--reflink=auto", source, options.target],
    cwd: options.target,
    environment: { PATH: process.env.PATH },
    timeoutMilliseconds: 60_000,
    maximumOutputBytes: 4096,
  });

  if (result.exitCode !== 0) {
    throw new Error("Workspace copy failed");
  }
}
