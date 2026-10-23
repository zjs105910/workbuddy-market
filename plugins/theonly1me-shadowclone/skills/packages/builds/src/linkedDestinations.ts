import path from "node:path";
import { firstLink, realPathOrNull, resolvedPath } from "@shadowclone/core";

export function skillDestinationsWithoutLinks(options: {
  readonly destinations: readonly string[];
  readonly source: string | null;
  readonly name: string;
  readonly homeDirectory: string;
}): { readonly targets: readonly string[]; readonly warnings: readonly string[] } {
  const unique = [...new Set(options.destinations)];
  const linked = unique.flatMap((destination) => {
    const link = firstLink(destination);

    return link ? [{ destination, link }] : [];
  });
  const targets = unique.filter((destination) => !linked.some((entry) => entry.destination === destination));
  const delivered = new Set([...targets.map(resolvedPath), ...(options.source ? [realPathOrNull(options.source) ?? options.source] : [])]);
  const display = (filePath: string): string =>
    filePath.startsWith(`${options.homeDirectory}${path.sep}`) ? `~/${path.relative(options.homeDirectory, filePath)}` : filePath;

  return {
    targets,
    warnings: linked.flatMap(({ destination, link }) =>
      delivered.has(resolvedPath(destination))
        ? []
        : [
            `${display(link.path)} is a link to ${display(link.target)}. Shadowclone does not write through links, so the agent that reads ${display(link.path)} does not get ${options.name} from this build.`,
          ],
    ),
  };
}
