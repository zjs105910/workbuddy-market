import { runProcess } from "@shadowclone/core";

const ignoredPaths = /(^|\/)(docs|playground|__tests__|test|tests|fixtures)\/|\.(test|spec)\.[cm]?[jt]sx?$|\.md$|CHANGELOG|(^|\/)(pnpm-lock\.yaml|package-lock\.json|yarn\.lock|bun\.lockb?)$/;

async function git(options: { readonly clone: string; readonly arguments: readonly string[] }): Promise<string> {
  const result = await runProcess({
    arguments: ["git", ...options.arguments],
    cwd: options.clone,
    environment: process.env,
    timeoutMilliseconds: 120_000,
  });

  return result.exitCode === 0 ? result.stdout : "";
}

type OldRange = { readonly path: string; readonly start: number; readonly end: number };

function oldRanges(diff: string): readonly OldRange[] {
  const ranges: OldRange[] = [];
  let path: string | null = null;

  for (const line of diff.split("\n")) {
    if (line.startsWith("--- ")) {
      path = line.startsWith("--- a/") ? line.slice(6) : null;
      continue;
    }

    const hunk = /^@@ -(\d+)(?:,(\d+))? \+/.exec(line);

    if (hunk && path !== null && !ignoredPaths.test(path)) {
      const start = Number(hunk[1]);
      const count = hunk[2] === undefined ? 1 : Number(hunk[2]);

      if (count > 0) {
        ranges.push({ path, start, end: start + count - 1 });
      } else if (start > 0) {
        ranges.push({ path, start, end: start });
      }
    }
  }

  return ranges;
}

export async function blamedPulls(options: { readonly clone: string; readonly fixCommit: string }): Promise<ReadonlyMap<number, number>> {
  const diff = await git({ clone: options.clone, arguments: ["diff", "--unified=0", "--no-color", `${options.fixCommit}^`, options.fixCommit] });
  const lineCounts = new Map<string, number>();

  for (const range of oldRanges(diff).slice(0, 60)) {
    const porcelain = await git({
      clone: options.clone,
      arguments: ["blame", "--line-porcelain", "-L", `${range.start},${range.end}`, `${options.fixCommit}^`, "--", range.path],
    });

    for (const match of porcelain.matchAll(/^([0-9a-f]{40}) \d+ \d+/gm)) {
      const sha = match[1] ?? "";
      lineCounts.set(sha, (lineCounts.get(sha) ?? 0) + 1);
    }
  }

  const pulls = new Map<number, number>();

  for (const [sha, count] of lineCounts) {
    const subject = await git({ clone: options.clone, arguments: ["log", "-1", "--format=%s", sha] });
    const number = Number(/\(#(\d+)\)\s*$/.exec(subject.trim())?.[1]);

    if (Number.isInteger(number) && number > 0) {
      pulls.set(number, (pulls.get(number) ?? 0) + count);
    }
  }

  return pulls;
}
