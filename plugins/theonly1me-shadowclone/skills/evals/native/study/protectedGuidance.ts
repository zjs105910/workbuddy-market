import { lstat, readlink } from "node:fs/promises";
import { treeFingerprint } from "../files";
import { fingerprint } from "../../shared/structured";

export async function protectedGuidanceFingerprint(paths: readonly string[]) {
  const values = [];
  for (const entry of paths) {
    if (entry.endsWith("/node_modules")) continue;
    const metadata = await lstat(entry).catch(() => null);
    const content = !metadata
      ? null
      : metadata.isDirectory()
        ? await treeFingerprint(entry)
        : metadata.isSymbolicLink()
          ? fingerprint(await readlink(entry))
          : new Bun.CryptoHasher("sha256")
              .update(await Bun.file(entry).arrayBuffer())
              .digest("hex");
    values.push([entry, metadata?.mode ?? null, content]);
  }
  return fingerprint(values);
}
