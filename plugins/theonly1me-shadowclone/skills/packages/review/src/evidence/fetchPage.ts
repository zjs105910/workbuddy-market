import { lookup } from "node:dns/promises";
import { isIP } from "node:net";
import { isPublicAddress } from "./addresses";

const maximumBytes = 3_000_000;
const maximumRedirects = 5;
const timeoutMilliseconds = 15_000;

const namedEntities: Readonly<Record<string, string>> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
};

async function resolvesToPublicAddresses(hostname: string): Promise<boolean> {
  const bare = hostname.replace(/^\[|\]$/g, "");

  if (isIP(bare) !== 0) {
    return isPublicAddress(bare);
  }

  const addresses = await lookup(bare, { all: true }).catch(() => []);

  return addresses.length > 0 && addresses.every((entry) => isPublicAddress(entry.address));
}

async function readLimited(response: Response): Promise<string | null> {
  const reader = response.body?.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;

  if (reader === undefined) {
    return "";
  }

  while (true) {
    const { done, value } = await reader.read();

    if (done) {
      return new TextDecoder().decode(Buffer.concat(chunks));
    }

    total += value.byteLength;

    if (total > maximumBytes) {
      await reader.cancel();
      return null;
    }

    chunks.push(value);
  }
}

export function htmlToText(html: string): string {
  return html
    .replace(/<(script|style|noscript)\b[\s\S]*?<\/\1>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&#x([0-9a-f]+);/gi, (_match, hex: string) => String.fromCodePoint(Number.parseInt(hex, 16)))
    .replace(/&#(\d+);/g, (_match, decimal: string) => String.fromCodePoint(Number(decimal)))
    .replace(/&([a-z]+);/gi, (match, name: string) => namedEntities[name.toLowerCase()] ?? match)
    .replace(/\s+/g, " ")
    .trim();
}

export async function fetchPageText(address: string): Promise<string | null> {
  let current: URL;

  try {
    current = new URL(address);
  } catch {
    return null;
  }

  for (let hop = 0; hop <= maximumRedirects; hop += 1) {
    if (!["https:", "http:"].includes(current.protocol) || !(await resolvesToPublicAddresses(current.hostname))) {
      return null;
    }

    const response = await fetch(current, {
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMilliseconds),
      headers: { "User-Agent": "shadowclone-review", Accept: "text/html,text/plain,application/json,*/*" },
    }).catch(() => null);

    if (response === null) {
      return null;
    }

    const location = response.headers.get("location");

    if (response.status >= 300 && response.status < 400 && location !== null) {
      current = new URL(location, current);
      continue;
    }

    const body = response.ok ? await readLimited(response) : null;

    return body !== null && (response.headers.get("content-type") ?? "").includes("html") ? htmlToText(body) : body;
  }

  return null;
}
