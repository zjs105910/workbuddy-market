import { chmod, lstat, mkdir, mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { confinedPath, requirePrivateDirectory, writeFrozenFile } from "../files";
import { mountReadOnlyWorkspace } from "../readOnlyWorkspace";
import { copyWorkspace, validateNativeFile } from "../workspace";
import { buildGitHistory } from "./git";
import type { RunArmName } from "./record";
import type { ArmEnvironment, StudySuite, StudyTask } from "./schema";

export const githubStub = (logFile: string) => `#!/usr/bin/env bun
import { appendFileSync, readFileSync } from "node:fs";
const args = process.argv.slice(2);
const bodyFileIndex = args.indexOf("--body-file");
const bodyFile = bodyFileIndex >= 0 ? args[bodyFileIndex + 1] : undefined;
let body = null;
if (bodyFile) {
  try { body = readFileSync(bodyFile === "-" ? 0 : bodyFile, "utf8"); } catch { body = null; }
}
appendFileSync(${JSON.stringify(logFile)}, JSON.stringify({ tool: "gh", args, body }) + "\\n");
if (args[0] === "pr" && args[1] === "create") { console.log("https://github.example/tally/pull/42"); process.exit(0); }
if (args[0] === "pr" && args[1] === "list") { console.log(args.includes("--json") ? "[]" : ""); process.exit(0); }
if (args[0] === "auth" && args[1] === "status") { console.log("Logged in to github.example"); process.exit(0); }
console.error("no pull requests found for branch");
process.exit(1);
`;

export type StudyWorkspace = {
  readonly directory: string;
  readonly homeDirectory: string;
  readonly toolDirectory: string;
  readonly writablePaths: readonly string[];
  readonly protectedPaths: readonly string[];
  readonly initialCommits: readonly string[];
  readonly skillPaths: Readonly<Record<string, string>>;
  readonly skillLocations: Readonly<Record<string, readonly string[]>>;
  readonly cleanup: () => Promise<void>;
};

function armFiles(options: { suite: StudySuite; arm: RunArmName; guidance?: ArmEnvironment }) {
  if (options.guidance) return options.guidance.files;
  return options.arm === "bare" || options.arm === "told"
    ? []
    : options.suite.arms[options.arm].files;
}

export async function createStudyWorkspace(options: {
  readonly suite: StudySuite;
  readonly task: StudyTask;
  readonly arm: RunArmName;
  readonly outputDirectory: string;
  readonly guidance?: ArmEnvironment;
}): Promise<StudyWorkspace> {
  await requirePrivateDirectory(options.outputDirectory);
  const container = await mkdtemp(path.join(options.outputDirectory, "candidate-"));
  const directory = path.join(container, "workspace");
  const homeDirectory = path.join(container, "home");
  const toolDirectory = path.join(homeDirectory, "bin");
  const origin = path.join(container, "origin.git");
  let mounted: Awaited<ReturnType<typeof mountReadOnlyWorkspace>> | null = null;

  try {
    await copyWorkspace({ source: options.suite.templateDirectory, target: directory });
    await mkdir(path.join(homeDirectory, "tmp"), { recursive: true, mode: 0o700 });
    await mkdir(toolDirectory, { mode: 0o700 });
    await Bun.write(
      path.join(toolDirectory, "gh"),
      githubStub(path.join(homeDirectory, "tmp/tool-calls.jsonl")),
    );
    await chmod(path.join(toolDirectory, "gh"), 0o700);
    const protectedPaths = [path.join(directory, "node_modules")];
    const skillLocations: Record<string, string[]> = {};

    for (const file of armFiles(options)) {
      validateNativeFile(file);
      const root = file.root === "home" ? homeDirectory : directory;
      const content =
        file.encoding === "utf8"
          ? file.content
              .replaceAll("{{home}}", homeDirectory)
              .replaceAll("{{workspace}}", directory)
          : file.content;
      await writeFrozenFile({ directory: root, file: { ...file, content } });
      const target = confinedPath({ directory: root, relative: file.path });
      protectedPaths.push(target);
      const skill = /(?:^|\/)skills\/([^/]+)\/SKILL\.md$/.exec(file.path);
      if (skill?.[1]) {
        const key = `${file.root}:${skill[1]}`;
        skillLocations[key] = [...(skillLocations[key] ?? []), target];
      }
    }

    for (const file of options.task.fixtures) {
      await writeFrozenFile({ directory, file });
    }

    if (options.guidance || (options.arm !== "bare" && options.arm !== "told")) {
      const memoryDirectory = path.join(homeDirectory, ".codex/memories");
      await mkdir(memoryDirectory, { recursive: true, mode: 0o700 });
      for (const file of options.suite.memory)
        await writeFrozenFile({ directory: memoryDirectory, file });
    }

    for (const name of [
      "AGENTS.md",
      "AGENTS.override.md",
      "CLAUDE.md",
      ".agents",
      ".codex",
      ".claude",
    ]) {
      if (await lstat(path.join(directory, name)).catch(() => null))
        protectedPaths.push(path.join(directory, name));
    }

    const initialCommits = options.task.git
      ? await buildGitHistory({ directory, origin, history: options.task.git })
      : [];
    mounted =
      options.task.mode === "advice"
        ? await mountReadOnlyWorkspace({ sourceDirectory: directory })
        : null;
    const active = mounted?.directory ?? directory;
    const relocate = (entry: string) =>
      entry.startsWith(`${directory}${path.sep}`)
        ? path.join(active, path.relative(directory, entry))
        : entry;
    const mount = mounted;

    return {
      directory: active,
      homeDirectory,
      toolDirectory,
      initialCommits,
      writablePaths: options.task.git && !mount ? [path.join(directory, ".git"), origin] : [],
      protectedPaths: protectedPaths.map(relocate),
      skillLocations: Object.fromEntries(
        Object.entries(skillLocations).map(([name, targets]) => [name, targets.map(relocate)]),
      ),
      skillPaths: Object.fromEntries(
        Object.entries(skillLocations).flatMap(([name, targets]) =>
          targets[0] ? [[name, relocate(targets[0])]] : [],
        ),
      ),
      cleanup: async () => {
        await mount?.cleanup();
        await rm(container, { recursive: true, force: true });
      },
    };
  } catch (error) {
    await mounted?.cleanup();
    await rm(container, { recursive: true, force: true });
    throw error;
  }
}
