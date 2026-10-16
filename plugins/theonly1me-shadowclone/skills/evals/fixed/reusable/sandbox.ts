import { mkdir, mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { runProcess } from "@shadowclone/core";
import { requirePrivateDirectory } from "../../native/files";
import { mountReadOnlyWorkspace } from "../../native/readOnlyWorkspace";
import { nativeFailure } from "../../native/diagnostics";
import { validateFixtures } from "../../native/study/validate";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { nativeSuite } from "./bridge";
import { readReusableSuite } from "./freeze";
import { validateGraders } from "./validation";
import { qualifyCodexSandbox } from "./nativeSandbox";

export async function validateReusableSuite(file: string) {
  const suite = await readReusableSuite(file);
  const directory = path.join(path.dirname(file), "validation");
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const graders = validateGraders(suite.cases);
  const fixtures = [];
  for (let offset = 0; offset < suite.cases.length; offset += 12) {
    fixtures.push(
      await validateFixtures({
        suite: nativeSuite({ suite, cases: suite.cases.slice(offset, offset + 12) }),
        outputDirectory: directory,
      }),
    );
  }
  const sandbox = await validateOfflineSandbox(directory);
  const nativeSandbox =
    suite.host.engine === "codex"
      ? await qualifyCodexSandbox({
          outputDirectory: directory,
          expectedCliVersion: suite.host.cliVersion,
        })
      : null;
  const result = {
    passed:
      graders.passed &&
      fixtures.every((result) => result.passed) &&
      sandbox.passed &&
      (nativeSandbox?.passed ?? true),
    graders,
    fixtures,
    sandbox,
    nativeSandbox,
  };
  await writeFrozenArtifact({ file: path.join(directory, "result.json"), value: result });
  return result;
}

export async function validateOfflineSandbox(outputDirectory: string) {
  const directory = await requirePrivateDirectory(outputDirectory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const root = await mkdtemp(path.join(directory, "sandbox-probe-"));
  const source = path.join(root, "workspace");
  const secret = path.join(root, "answers.json");
  await mkdir(source, { mode: 0o700 });
  await Bun.write(path.join(source, "input.txt"), "synthetic input");
  await Bun.write(secret, "synthetic grading answer");
  try {
    const mounted = await mountReadOnlyWorkspace({ sourceDirectory: source });
    try {
      const profile = `(version 1)(allow default)(deny network*)(deny file-read* (literal ${JSON.stringify(secret)}))(deny file-write* (subpath ${JSON.stringify(mounted.directory)}))`;
      const read = await runProcess({
        arguments: [
          "sandbox-exec",
          "-p",
          profile,
          "/bin/cat",
          path.join(mounted.directory, "input.txt"),
        ],
        cwd: root,
        environment: { PATH: process.env.PATH },
        timeoutMilliseconds: 10000,
        maximumOutputBytes: 4096,
      });
      const denied = await runProcess({
        arguments: ["sandbox-exec", "-p", profile, "/bin/cat", secret],
        cwd: root,
        environment: { PATH: process.env.PATH },
        timeoutMilliseconds: 10000,
        maximumOutputBytes: 4096,
      });
      const write = await runProcess({
        arguments: ["/usr/bin/touch", path.join(mounted.directory, "forbidden.txt")],
        cwd: root,
        environment: { PATH: process.env.PATH },
        timeoutMilliseconds: 10000,
        maximumOutputBytes: 4096,
      });
      return {
        passed:
          read.exitCode === 0 &&
          read.stdout === "synthetic input" &&
          denied.exitCode !== 0 &&
          write.exitCode !== 0,
        inputReadable: read.exitCode === 0,
        answersDenied: denied.exitCode !== 0,
        workspaceReadOnly: write.exitCode !== 0,
      };
    } finally {
      await mounted.cleanup();
    }
  } catch (error) {
    const diagnosticFile = path.join(directory, "sandbox-diagnostic.json");
    await writeFrozenArtifact({
      file: diagnosticFile,
      value: nativeFailure({ stage: "setup", error }),
    });
    return {
      passed: false,
      diagnosticFile,
      inputReadable: false,
      answersDenied: false,
      workspaceReadOnly: false,
    };
  } finally {
    await rm(root, { recursive: true, force: true });
  }
}

export async function readValidation(file: string) {
  return readFrozenArtifact(path.join(path.dirname(file), "validation/result.json"));
}
