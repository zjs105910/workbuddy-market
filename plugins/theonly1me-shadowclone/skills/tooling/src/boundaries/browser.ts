import { resolveRelativeImport, type ImportEdge } from "./imports";

const browserClientFolder = "packages/web/src/client/";

export const browserSubpath = "./browser";

function stemOf(file: string): string {
  return file.replace(/\.ts$/, "").replace(/\/index$/, "");
}

export function browserReachableFiles(edges: readonly ImportEdge[]): ReadonlySet<string> {
  const edgesByFile = new Map<string, ImportEdge[]>();

  for (const edge of edges) {
    edgesByFile.set(edge.file, [...(edgesByFile.get(edge.file) ?? []), edge]);
  }

  const filesByStem = new Map([...edgesByFile.keys()].map((file) => [stemOf(file), file]));
  const reachable = new Set(
    [...edgesByFile.keys()].filter((file) => file.startsWith(browserClientFolder)),
  );
  const pending = [...reachable];

  for (const file of pending) {
    for (const edge of (edgesByFile.get(file) ?? []).filter((candidate) => !candidate.typeOnly)) {
      const target = resolveRelativeImport(edge);
      const targetFile = target === null ? undefined : filesByStem.get(stemOf(target));

      if (targetFile !== undefined && !reachable.has(targetFile)) {
        reachable.add(targetFile);
        pending.push(targetFile);
      }
    }
  }

  return reachable;
}
