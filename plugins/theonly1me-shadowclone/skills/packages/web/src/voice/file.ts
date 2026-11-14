import { lstat, mkdir, open, readlink } from "node:fs/promises";
import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";

export type VoiceFileState = {
  readonly path: string;
  readonly state: "missing" | "file" | "link";
  readonly target: string | null;
};

function isMissing(error: unknown): boolean {
  return typeof error === "object" && error !== null && "code" in error && error.code === "ENOENT";
}

export function voiceFilePath(paths: ProjectPaths): string {
  return path.join(path.dirname(paths.shadowcloneDirectory), ".agents", "voice.md");
}

export async function voiceFileState(paths: ProjectPaths): Promise<VoiceFileState> {
  const file = voiceFilePath(paths);

  try {
    const stats = await lstat(file);

    return stats.isSymbolicLink()
      ? { path: file, state: "link", target: await readlink(file) }
      : { path: file, state: "file", target: null };
  } catch (error) {
    if (isMissing(error)) return { path: file, state: "missing", target: null };

    throw error;
  }
}

export async function writeVoiceFile(options: { readonly paths: ProjectPaths; readonly content: string }): Promise<string> {
  const current = await voiceFileState(options.paths);

  if (current.state !== "missing") {
    throw new Error(
      `${current.path} already exists${current.target ? ` as a link to ${current.target}` : ""}, so Shadowclone did not change it`,
    );
  }

  await mkdir(path.dirname(current.path), { recursive: true });

  const handle = await open(current.path, "wx", 0o600);

  try {
    await handle.writeFile(options.content);
  } finally {
    await handle.close();
  }

  return current.path;
}
