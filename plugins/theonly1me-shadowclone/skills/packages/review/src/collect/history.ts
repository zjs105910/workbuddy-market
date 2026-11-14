import { redactSecrets } from "@shadowclone/redact";
import { readGit } from "./git";

const maximumFiles = 15;

export async function readHistory(options: {
  readonly checkout: string;
  readonly baseSha: string;
  readonly paths: readonly string[];
}): Promise<string> {
  const sections: string[] = [];

  for (const filePath of options.paths.slice(0, maximumFiles)) {
    const log = await readGit({
      checkout: options.checkout,
      arguments: [
        "log",
        "-n",
        "3",
        "--no-merges",
        "--date=short",
        "--format=%h %ad %s",
        options.baseSha,
        "--",
        filePath,
      ],
    });

    if (log.trim().length > 0) {
      sections.push(`${filePath}\n${log.trim()}`);
    }
  }

  return redactSecrets({ text: sections.join("\n\n") });
}
