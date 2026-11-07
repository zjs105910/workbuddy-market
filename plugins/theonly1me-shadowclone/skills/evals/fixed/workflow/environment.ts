import { mkdir } from "node:fs/promises";
import path from "node:path";
import { initialize } from "@shadowclone/cli";
import { installIntegration, syncLearningEnvironment } from "@shadowclone/environment";
import { ownedWrite } from "@shadowclone/core";
import { fingerprint } from "../../shared/structured";
import type { NativeEngine } from "@shadowclone/agents";
import type { ArmEnvironment } from "../../native/study/schema";
import { existingSkill, workflowDefinition } from "./definition";
import { workflowLayout, captureWorkflowArm } from "./layout";

export async function writeExistingLibrary(options: { directory: string; arm: string }) {
  const layout = workflowLayout(options.directory);
  await mkdir(layout.workspace(options.arm), { recursive: true, mode: 0o700 });
  await ownedWrite({ path: path.join(layout.workspace(options.arm), "AGENTS.md"), content: workflowDefinition.repositoryInstructions });
  await ownedWrite({ path: path.join(layout.workspace(options.arm), "CLAUDE.md"), content: "@AGENTS.md\n" });
  for (const root of [".agents", ".claude"]) {
    await ownedWrite({ path: path.join(layout.home(options.arm), root, "skills/personal-engineering/SKILL.md"), content: existingSkill });
  }
}

export async function initializeRouting(options: { directory: string; arm: string }) {
  const layout = workflowLayout(options.directory);
  const paths = layout.paths(options.arm);
  await initialize({ paths, workingDirectory: layout.workspace(options.arm), agents: [],
    consent: { learn: false, skills: true, background: false },
    presence: { hasRepositoryGuidance: true, presentCaptureSources: new Set() },
    runner: async () => { throw new Error("Routing preparation must not make a model call"); }, writeLine: () => {} });
  for (const agent of ["codex", "claude-code"] as const) {
    await installIntegration({ paths, agent, scope: "global", cwd: layout.workspace(options.arm) });
  }
  await syncLearningEnvironment(paths);
}

export function requireExistingSkillPreserved(options: { original: ArmEnvironment; candidate: ArmEnvironment }) {
  for (const source of options.original.files.filter(file => file.path.includes("/personal-engineering/"))) {
    const candidate = options.candidate.files.find(file => file.root === source.root && file.path === source.path);
    if (!candidate || candidate.content !== source.content || candidate.encoding !== source.encoding) throw new Error("Preparation changed an existing manual skill");
  }
}

export async function captureStartingEnvironments(directory: string) {
  const capture = async (engine: NativeEngine) => {
    const original = await captureWorkflowArm({ directory, arm: "original", engine });
    const routing = await captureWorkflowArm({ directory, arm: "routing", engine });
    const deep = await captureWorkflowArm({ directory, arm: "deep", engine });
    requireExistingSkillPreserved({ original, candidate: routing });
    requireExistingSkillPreserved({ original, candidate: deep });
    if (fingerprint(routing.files) !== fingerprint(deep.files)) throw new Error("Deep learning must start from the identical routed guidance");
    return { original, "first-time": routing };
  };
  return { codex: await capture("codex"), "claude-code": await capture("claude-code") };
}

export async function materializeCorrections(directory: string) {
  const layout = workflowLayout(directory);
  const paths = layout.paths("deep");
  for (const [sessionIndex, session] of workflowDefinition.corrections.entries()) {
    const records = session.messages.map((message, messageIndex) => ({ type: message.role, sessionId: session.sessionId,
      uuid: `${session.sessionId}-${messageIndex}`, timestamp: new Date(Date.UTC(2026, 8, 1 + sessionIndex, 10, messageIndex)).toISOString(),
      cwd: layout.workspace("deep"), message: { content: message.text } }));
    await ownedWrite({ path: path.join(paths.claudeProjectsDirectory, "synthetic-persona", `${session.sessionId}.jsonl`),
      content: `${records.map(record => JSON.stringify(record)).join("\n")}\n` });
  }
}
