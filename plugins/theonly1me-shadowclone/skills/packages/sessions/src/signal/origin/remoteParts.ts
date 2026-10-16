type RemoteParts = {
  readonly host: string;
  readonly owner: string;
  readonly repository: string;
};

function splitRemotePath(remotePath: string): {
  readonly owner: string;
  readonly repository: string;
} | null {
  let decoded: string[];

  try {
    decoded = remotePath
      .split("/")
      .filter(Boolean)
      .map((segment) => decodeURIComponent(segment));
  } catch {
    return null;
  }

  const segments = decoded;
  const repository = segments.at(-1);

  if (repository === undefined || segments.length < 2) {
    return null;
  }

  if (
    segments.some(
      (segment) =>
        segment === "." ||
        segment === ".." ||
        [...segment].some((character) => character.charCodeAt(0) <= 32) ||
        segment.includes("/") ||
        segment.includes("\\"),
    )
  ) {
    return null;
  }

  return {
    owner: segments.slice(0, -1).join("/"),
    repository: repository.replace(/\.git$/, ""),
  };
}

function urlRemoteParts(remote: string): RemoteParts | null {
  let parsed: URL;

  try {
    parsed = new URL(remote);
  } catch {
    return null;
  }

  if (parsed.hostname.length === 0) {
    return null;
  }

  const parts = splitRemotePath(parsed.pathname);

  return parts === null
    ? null
    : {
        host:
          parsed.port.length > 0
            ? `${parsed.hostname}:${parsed.port}`
            : parsed.hostname,
        owner: parts.owner,
        repository: parts.repository,
      };
}

function secureShellRemoteParts(remote: string): RemoteParts | null {
  const match = remote.match(/^(?:[^@/]+@)?([^/:]+):([^/].*)$/);

  if (!match) {
    return null;
  }

  const [, host, remotePath] = match;

  if (!host || !remotePath) {
    return null;
  }

  const parts = splitRemotePath(remotePath);

  return parts === null
    ? null
    : { host, owner: parts.owner, repository: parts.repository };
}

export function remoteParts(remote: string): RemoteParts | null {
  const trimmed = remote.trim();

  return urlRemoteParts(trimmed) ?? secureShellRemoteParts(trimmed);
}
