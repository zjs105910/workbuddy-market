import path from "node:path";
import type { NativeEngine } from "@shadowclone/agents";
import { captureArm } from "../../native/study/prepare/freeze";
import { createProjectPaths } from "@shadowclone/core";

export function workflowLayout(directory: string) {
  const home = (arm: string) => path.join(directory, "homes", arm);
  const workspace = (arm: string) => path.join(directory, "workspaces", arm);
  const paths = (arm: string) => createProjectPaths({ homeDirectory: home(arm), platform: process.platform });
  return { home, workspace, paths, template: path.join(directory, "template"), preparation: path.join(directory, "preparation.json"),
    environments: path.join(directory, "environments.json"), learning: path.join(directory, "learning") };
}

export async function captureWorkflowArm(options: { directory: string; arm: string; engine: NativeEngine }) {
  const layout = workflowLayout(options.directory);
  return captureArm({ home: layout.home(options.arm), workspace: layout.workspace(options.arm), sourceHome: layout.home(options.arm), engine: options.engine });
}
