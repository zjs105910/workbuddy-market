import { remoteParts } from "./remoteParts";
import { runHostCommand } from "@shadowclone/core";
import type { OriginScope, RepositoryIdentity } from "../types";

export type GitRemoteReader = (cwd: string) => Promise<string | null>;

const edgeSeparators = "._-";

function withoutEdgeSeparators(value: string): string {
  let start = 0;
  let end = value.length;

  while (start < end && edgeSeparators.includes(value.charAt(start))) {
    start += 1;
  }

  while (end > start && edgeSeparators.includes(value.charAt(end - 1))) {
    end -= 1;
  }

  return value.slice(start, end);
}

export function isolatedOrigin(key: string): OriginScope {
  const digest = new Bun.CryptoHasher("sha256")
    .update(key)
    .digest("hex")
    .slice(0, 16);

  return {
    id: `isolated:${digest}`,
    directoryName: `isolated--${digest}`,
    promotable: false,
  };
}

export function normalizeRemoteOrigin(remote: string): OriginScope | null {
  const parts = remoteParts(remote);

  if (parts === null) {
    return null;
  }

  const host = parts.host.toLowerCase();
  const owner = ["github.com", "gitlab.com"].includes(host)
    ? parts.owner.toLowerCase()
    : parts.owner;
  const id = `${host}/${owner}`;
  const directoryName = originDirectoryName(id);

  return { id, directoryName, promotable: true };
}

export function normalizeRemoteRepository(
  remote: string,
): RepositoryIdentity | null {
  const parts = remoteParts(remote);
  const origin = normalizeRemoteOrigin(remote);

  if (parts === null || origin === null) {
    return null;
  }

  const name = ["github.com", "gitlab.com"].includes(parts.host.toLowerCase())
    ? parts.repository.toLowerCase()
    : parts.repository;
  const id = `${origin.id}/${name}`;
  const safeName =
    withoutEdgeSeparators(name.replace(/[^a-z0-9._-]+/g, "--")).slice(0, 64) || "repository";
  const digest = new Bun.CryptoHasher("sha256")
    .update(id)
    .digest("hex")
    .slice(0, 16);

  return {
    id,
    name,
    profileFileName: `${safeName}--${digest}`,
    origin,
  };
}

export async function readGitRemote(cwd: string): Promise<string | null> {
  try {
    const { exitCode, stdout } = await runHostCommand({
      arguments: [
        "git",
        "-C",
        cwd,
        "config",
        "--local",
        "--get",
        "remote.origin.url",
      ],
      cwd,
    });

    const value = stdout.trim();

    return exitCode === 0 && value.length > 0 ? value : null;
  } catch {
    return null;
  }
}

export function originDirectoryName(id: string): string {
  if (id.startsWith("isolated:")) {
    return id.replace(":", "--");
  }

  const digest = new Bun.CryptoHasher("sha256")
    .update(id)
    .digest("hex")
    .slice(0, 16);

  return `${id
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "--")
    .slice(0, 80)}--${digest}`;
}
