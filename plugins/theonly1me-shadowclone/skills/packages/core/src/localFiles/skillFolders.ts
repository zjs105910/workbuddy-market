import { rmdir } from "node:fs/promises";
import path from "node:path";

function skillFolderOf(filePath: string): string | null {
  const parts = filePath.split(path.sep);
  const index = parts.lastIndexOf("skills");

  if (index < 1 || index + 2 >= parts.length) {
    return null;
  }

  const owner = parts[index - 1] ?? "";
  const build = parts
    .slice(0, index - 1)
    .join(path.sep)
    .endsWith(`${path.sep}.shadowclone${path.sep}builds`);

  return owner.startsWith(".") || owner === "config" || build
    ? parts.slice(0, index + 2).join(path.sep)
    : null;
}

export async function removeEmptySkillFolders(filePath: string): Promise<void> {
  const skillFolder = skillFolderOf(filePath);

  if (skillFolder === null) {
    return;
  }

  for (
    let directory = path.dirname(filePath);
    directory.length >= skillFolder.length;
    directory = path.dirname(directory)
  ) {
    const removed = await rmdir(directory).then(
      () => true,
      () => false,
    );

    if (!removed) {
      return;
    }
  }
}
