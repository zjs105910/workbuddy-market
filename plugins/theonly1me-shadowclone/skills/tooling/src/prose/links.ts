import { stat } from "node:fs/promises";
import path from "node:path";
import { markdownLines } from "./markdownLines";
import { headingSlugs } from "./slugs";

export type LinkFinding = {
  readonly file: string;
  readonly line: number;
  readonly message: string;
};

type Link = {
  readonly line: number;
  readonly target: string;
};

type ResolvedLink = {
  readonly targetFile: string;
  readonly anchor: string;
};

const inlineLink = /!?\[[^\]]*\]\(\s*(<[^>]*>|[^)\s]*)[^)]*\)/g;
const referenceDefinition = /^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)/;
const externalTarget = /^(?:[a-z][a-z0-9+.-]*:|\/\/)/i;

function cleanTarget(raw: string): string {
  const unwrapped = raw.startsWith("<") ? raw.slice(1, -1) : raw;

  try {
    return decodeURI(unwrapped);
  } catch {
    return unwrapped;
  }
}

function linksOf(text: string): readonly Link[] {
  const links: Link[] = [];

  for (const line of markdownLines(text)) {
    if (line.inFence) {
      continue;
    }

    const withoutCode = line.text.replace(/`+[^`]*`+/g, "");
    const definition = referenceDefinition.exec(withoutCode)?.[1];

    if (definition !== undefined) {
      links.push({ line: line.number, target: cleanTarget(definition) });
    }

    for (const match of withoutCode.matchAll(inlineLink)) {
      links.push({ line: line.number, target: cleanTarget(match[1] ?? "") });
    }
  }

  return links;
}

function resolveLink(options: { readonly file: string; readonly target: string }): ResolvedLink {
  const [reference = "", anchor = ""] = options.target.split("#", 2);
  const location = reference.split("?")[0] ?? "";

  if (location === "") {
    return { targetFile: options.file, anchor };
  }

  const targetFile = location.startsWith("/")
    ? location.slice(1)
    : path.posix.normalize(path.posix.join(path.posix.dirname(options.file), location));

  return { targetFile, anchor };
}

async function exists(location: string): Promise<boolean> {
  return stat(location).then(
    () => true,
    () => false,
  );
}

export async function linkFindings(options: {
  readonly rootDirectory: string;
  readonly files: readonly string[];
}): Promise<readonly LinkFinding[]> {
  const findings: LinkFinding[] = [];
  const slugCache = new Map<string, ReadonlySet<string>>();

  async function slugsOf(file: string): Promise<ReadonlySet<string>> {
    const cached = slugCache.get(file);

    if (cached !== undefined) {
      return cached;
    }

    const slugs = headingSlugs(await Bun.file(path.join(options.rootDirectory, file)).text());

    slugCache.set(file, slugs);

    return slugs;
  }

  for (const file of options.files) {
    const text = await Bun.file(path.join(options.rootDirectory, file)).text();

    for (const link of linksOf(text)) {
      if (link.target === "" || externalTarget.test(link.target)) {
        continue;
      }

      const { targetFile, anchor } = resolveLink({ file, target: link.target });

      if (!(await exists(path.join(options.rootDirectory, targetFile)))) {
        findings.push({
          file,
          line: link.line,
          message: `target ${link.target} does not exist`,
        });
      } else if (anchor !== "" && targetFile.endsWith(".md")) {
        if (!(await slugsOf(targetFile)).has(anchor.toLowerCase())) {
          findings.push({
            file,
            line: link.line,
            message: `heading #${anchor} does not exist in ${targetFile}`,
          });
        }
      }
    }
  }

  return findings;
}
