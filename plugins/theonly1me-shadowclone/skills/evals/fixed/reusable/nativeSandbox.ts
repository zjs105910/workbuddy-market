import { mkdir, mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { nativeCodexArguments } from "@shadowclone/agents";
import { runProcess } from "@shadowclone/core";
import { requirePrivateDirectory } from "../../native/files";
import { writeFrozenArtifact } from "../workflow/preparation";

const probeCommand =
  'cat "$1" >/dev/null 2>&1; input=$?; touch "$2" 2>/dev/null; workspace=$?; touch "$3" 2>/dev/null; temporary=$?; touch "$4" 2>/dev/null; outside=$?; cat "$5" >/dev/null 2>&1; outside_read=$?; cat "$6" >/dev/null 2>&1; answers=$?; touch "$7" 2>/dev/null; guidance=$?; printf "%s %s %s %s %s %s %s\\n" "$input" "$workspace" "$temporary" "$outside" "$outside_read" "$answers" "$guidance"';

export async function qualifyCodexSandbox(options: {
  outputDirectory: string;
  expectedCliVersion: string;
}) {
  const outputDirectory = await requirePrivateDirectory(options.outputDirectory);
  const root = await mkdtemp(path.join(outputDirectory, "native-codex-probe-"));
  const outsideRoot = await mkdtemp("/private/tmp/shadowclone-native-outside-");
  try {
    const directory = path.join(root, "workspace");
    const homeDirectory = path.join(root, "home");
    await mkdir(directory, { mode: 0o700 });
    await mkdir(path.join(homeDirectory, "tmp"), { recursive: true, mode: 0o700 });
    await mkdir(path.join(homeDirectory, ".codex"), { mode: 0o700 });
    const inputFile = path.join(directory, "input.txt");
    const guidanceFile = path.join(directory, "AGENTS.md");
    const answerFile = path.join(root, "answers.json");
    const outsideFile = path.join(outsideRoot, "private.txt");
    for (const file of [inputFile, guidanceFile, answerFile, outsideFile])
      await Bun.write(file, "synthetic fixture", { mode: 0o600 });
    const environment = {
      PATH: process.env.PATH,
      HOME: homeDirectory,
      CODEX_HOME: path.join(homeDirectory, ".codex"),
      TMPDIR: path.join(homeDirectory, "tmp"),
    };
    const version = await runProcess({
      arguments: ["codex", "--version"],
      cwd: directory,
      environment,
      timeoutMilliseconds: 10000,
      maximumOutputBytes: 4096,
    });
    const probes = [];
    for (const access of ["write", "read"] as const)
      for (const memoryEnabled of [false, true]) {
        const native = nativeCodexArguments({
          engine: "codex",
          directory,
          homeDirectory,
          memoryEnabled,
          access,
          blockedPaths: [root],
          protectedPaths: [guidanceFile],
          prompt: "unused",
        });
        const configurations: string[] = [];
        for (const [index, argument] of native.entries()) {
          const configuration = native[index + 1];
          if (argument === "-c" && configuration !== undefined)
            configurations.push("-c", configuration);
        }
        const response = await runProcess({
          arguments: [
            "codex",
            "sandbox",
            "-C",
            directory,
            "-P",
            "native-evaluation",
            ...configurations,
            "/bin/sh",
            "-c",
            probeCommand,
            "probe",
            inputFile,
            path.join(directory, "created.txt"),
            path.join(homeDirectory, "tmp/allowed.txt"),
            path.join(outsideRoot, "created.txt"),
            outsideFile,
            answerFile,
            guidanceFile,
          ],
          cwd: directory,
          environment,
          timeoutMilliseconds: 10000,
          maximumOutputBytes: 4096,
        });
        const statuses = response.stdout.trim().split(/\s+/);
        const [input, workspace, temporary, outside, outsideRead, answers, guidance] = statuses;
        const denied = (status: string | undefined) =>
          status !== undefined && /^\d+$/.test(status) && status !== "0";
        const passed =
          version.exitCode === 0 &&
          version.stdout.trim() === options.expectedCliVersion &&
          response.exitCode === 0 &&
          statuses.length === 7 &&
          input === "0" &&
          (access === "write" ? workspace === "0" : denied(workspace)) &&
          temporary === "0" &&
          denied(outside) &&
          denied(outsideRead) &&
          denied(answers) &&
          denied(guidance);
        probes.push({
          access,
          memoryEnabled,
          passed,
          stdout: response.stdout,
          stderr: response.stderr,
        });
      }
    await writeFrozenArtifact({
      file: path.join(outputDirectory, "native-codex-sandbox.json"),
      value: { cliVersion: version.stdout.trim(), probes },
    });
    return {
      passed: probes.every((probe) => probe.passed),
      probes: probes.map((probe) => ({
        access: probe.access,
        memoryEnabled: probe.memoryEnabled,
        passed: probe.passed,
      })),
      modelCalls: 0,
    };
  } finally {
    await rm(outsideRoot, { recursive: true, force: true });
    await rm(root, { recursive: true, force: true });
  }
}
