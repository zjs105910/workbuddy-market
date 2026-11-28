import { lstat } from "node:fs/promises";
import path from "node:path";
import { fingerprint } from "../../../shared/structured";
import type { NativeFile } from "../../schema";
import { validateNativeFile } from "../../workspace";
import type { ArmEnvironment } from "../schema";

const origins = {
  codex: [
    { root: "home" as const, patterns: [".codex/AGENTS{,.override}.md", ".agents/skills/**/*", ".codex/skills/**/*"] },
    { root: "workspace" as const, patterns: ["AGENTS{,.override}.md", ".agents/skills/**/*"] },
  ],
  "claude-code": [
    { root: "home" as const, patterns: [".claude/CLAUDE.md", ".claude/skills/**/*", ".agents/skills/**/*"] },
    { root: "workspace" as const, patterns: ["AGENTS{,.override}.md", "CLAUDE.md", ".claude/skills/**/*", ".agents/skills/**/*"] },
  ],
} as const;

function portable(options: { content: string; home: string; workspace: string; sourceHome: string }): string {
  let content = options.content.replaceAll(options.home, "{{home}}").replaceAll(options.workspace, "{{workspace}}");

  for (const agent of [".agents", ".claude", ".codex"]) {
    content = content.replaceAll(path.join(options.sourceHome, agent), `{{home}}/${agent}`);
  }

  return content;
}

export async function captureArm(options: {
  readonly home: string;
  readonly workspace: string;
  readonly sourceHome: string;
  readonly engine?: "codex" | "claude-code";
}): Promise<ArmEnvironment> {
  const files: NativeFile[] = [];

  for (const origin of origins[options.engine ?? "codex"]) {
    const directory = origin.root === "home" ? options.home : options.workspace;

    for (const pattern of origin.patterns) {
      for await (const relative of new Bun.Glob(pattern).scan({ cwd: directory, dot: true, onlyFiles: true, followSymlinks: false })) {
        if (relative.includes("/shadowclone-context/") || relative.split("/").includes(".system")) {
          continue;
        }

        const filePath = path.join(directory, relative);
        const metadata = await lstat(filePath);

        if (metadata.isSymbolicLink()) {
          throw new Error("Study guidance contains a symbolic link");
        }

        const bytes = await Bun.file(filePath).bytes();
        const binary = bytes.includes(0);
        const content = binary ? Buffer.from(bytes).toString("base64")
          : portable({ content: new TextDecoder().decode(bytes), home: options.home, workspace: options.workspace, sourceHome: options.sourceHome });
        const file: NativeFile = { root: origin.root, path: relative, content, encoding: binary ? "base64" : "utf8", mode: metadata.mode & 0o777 };
        validateNativeFile(file);
        files.push(file);
      }
    }
  }

  const sorted = files.toSorted((left, right) => `${left.root}/${left.path}`.localeCompare(`${right.root}/${right.path}`));
  const destinations = sorted.map((file) => `${file.root}/${file.path}`);

  if (new Set(destinations).size !== destinations.length) {
    throw new Error("Duplicate study guidance destination");
  }

  return { files: sorted, fingerprint: fingerprint(sorted) };
}
