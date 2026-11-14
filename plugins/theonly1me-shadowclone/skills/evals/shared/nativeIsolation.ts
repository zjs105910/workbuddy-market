import path from "node:path";
import { stripManagedGuidance } from "@shadowclone/environment";
import { companionPrefix, restoreOriginalSkill } from "@shadowclone/skills";

export async function isolateNativeGuidance(directory: string): Promise<void> {
  for await (const relative of new Bun.Glob("**/SKILL.md").scan({
    cwd: directory,
    dot: true,
    onlyFiles: true,
  })) {
    const file = Bun.file(path.join(directory, relative));

    if (
      relative
        .split(path.sep)
        .some((segment) => segment.startsWith(companionPrefix))
    ) {
      await file.delete();

      continue;
    }

    const text = await file.text();
    const original = restoreOriginalSkill(text);

    if (original !== text) {
      await Bun.write(file, original);
    }
  }

  const files = new Bun.Glob(
    "**/{AGENTS.md,AGENTS.override.md,CLAUDE.md,CLAUDE.local.md}",
  );

  for await (const relative of files.scan({
    cwd: directory,
    dot: true,
    onlyFiles: true,
  })) {
    const file = Bun.file(path.join(directory, relative));
    const text = await file.text();
    const isolated = stripManagedGuidance(text);

    if (
      isolated.includes("# Shadowclone profile") ||
      isolated.includes("shadowclone hook")
    ) {
      throw new Error(
        "Unmanaged Shadowclone injection prevents an isolated evaluation",
      );
    }

    if (text !== isolated) {
      await Bun.write(file, isolated);
    }
  }
}
