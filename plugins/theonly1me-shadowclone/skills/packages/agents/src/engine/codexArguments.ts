import path from "node:path";
import { canonicalPath } from "@shadowclone/core";
import { evaluationCommand } from "./evaluationIsolation";
import { userCodexHome } from "./codexHome";
import { validateEngineExecution } from "./execution";
import type { EngineRunOptions, PermissionMode } from "./types";

const evaluationProfileName = "shadowclone-evaluation";
const reviewProfileName = "shadowclone-review";

function reviewPermissionValue(options: { readonly cwd: string; readonly hiddenPaths: readonly string[] }): string {
  const filesystem = [
    `${JSON.stringify(":root")}="deny"`,
    `${JSON.stringify(":minimal")}="read"`,
    `${JSON.stringify(canonicalPath(options.cwd))}="read"`,
    ...options.hiddenPaths.map((hiddenPath) => `${JSON.stringify(canonicalPath(hiddenPath))}="deny"`),
  ];

  return `{extends=":read-only",filesystem={${filesystem.join(",")}},network={enabled=false}}`;
}

function validateCodexReview(options: EngineRunOptions): void {
  if (options.systemPromptFile !== undefined) {
    throw new Error("Review cannot load a system prompt file");
  }

  if (options.permissionMode !== "dontAsk") {
    throw new Error("Review requires the dontAsk permission mode");
  }
}

export function validateCodexOptions(options: EngineRunOptions): void {
  if (options.execution.purpose === "review") {
    validateCodexReview(options);
  } else {
    validateEngineExecution(options);
  }

  if (options.sessionId !== undefined) {
    throw new Error("Codex cannot set a caller-provided session id");
  }

  if (options.maxBudgetUsd !== undefined) {
    throw new Error("Codex cannot enforce a per-run dollar budget");
  }

  if (options.disallowedTools && options.disallowedTools.length > 0) {
    throw new Error("Codex cannot enforce a granular tool denylist");
  }

  if (options.allowedTools && options.allowedTools.length > 0) {
    throw new Error("Codex cannot enforce a granular tool allowlist");
  }

  const supportedModes: readonly (PermissionMode | undefined)[] = [
    undefined,
    "dontAsk",
    "plan",
  ];

  if (!supportedModes.includes(options.permissionMode)) {
    throw new Error("Codex cannot honor this permission mode");
  }
}

export function isCodexEvaluationExecution(run: EngineRunOptions): boolean {
  return (
    run.execution.purpose === "evaluation" && run.execution.access === "write"
  );
}

function evaluationPermissionValue(options: {
  readonly run: EngineRunOptions;
  readonly temporaryDirectory: string;
}): string {
  const blockedPaths =
    options.run.execution.purpose === "evaluation"
      ? (options.run.execution.blockedPaths ?? [])
      : [];
  const filesystem = [
    `${JSON.stringify(":root")}="deny"`,
    `${JSON.stringify(":minimal")}="read"`,
    ...blockedPaths.map(
      (blockedPath) => `${JSON.stringify(canonicalPath(blockedPath))}="deny"`,
    ),
    `${JSON.stringify(canonicalPath(options.run.cwd))}="write"`,
    `${JSON.stringify(canonicalPath(options.temporaryDirectory))}="write"`,
  ];

  return `{extends=":workspace",filesystem={${filesystem.join(",")}},network={enabled=false}}`;
}

function shellEnvironmentValue(temporaryDirectory: string): string {
  const values = {
    TMPDIR: temporaryDirectory,
    NX_SOCKET_DIR: path.join(temporaryDirectory, "nx"),
    NODE_COMPILE_CACHE: path.join(temporaryDirectory, "node-cache"),
    XDG_CACHE_HOME: path.join(temporaryDirectory, "cache"),
  };
  const entries = Object.entries(values).map(
    ([key, value]) => `${key}=${JSON.stringify(value)}`,
  );

  return `{inherit="core",ignore_default_excludes=false,set={${entries.join(",")}}}`;
}

export function buildCodexArguments(options: {
  readonly run: EngineRunOptions;
  readonly outputSchemaPath?: string;
  readonly temporaryDirectory?: string;
}): readonly string[] {
  validateCodexOptions(options.run);

  const evaluationExecution = isCodexEvaluationExecution(options.run);

  if (evaluationExecution && !options.temporaryDirectory) {
    throw new Error(
      "Codex evaluation requires an isolated temporary directory",
    );
  }

  const arguments_ = [
    "codex",
    "exec",
    "-",
    "--json",
    "-C",
    options.run.cwd,
    "--skip-git-repo-check",
    "-c",
    'approval_policy="never"',
    "-c",
    "mcp_servers={}",
  ];

  if (evaluationExecution && options.temporaryDirectory) {
    arguments_.push(
      "-c",
      `default_permissions=${JSON.stringify(evaluationProfileName)}`,
      "-c",
      `permissions.${evaluationProfileName}=${evaluationPermissionValue({ run: options.run, temporaryDirectory: options.temporaryDirectory })}`,
      "-c",
      `shell_environment_policy=${shellEnvironmentValue(options.temporaryDirectory)}`,
    );
  } else if (options.run.execution.purpose === "review") {
    arguments_.push(
      "-c",
      `default_permissions=${JSON.stringify(reviewProfileName)}`,
      "-c",
      `permissions.${reviewProfileName}=${reviewPermissionValue({
        cwd: options.run.cwd,
        hiddenPaths: [userCodexHome(), ...(options.temporaryDirectory ? [options.temporaryDirectory] : [])],
      })}`,
      "-c",
      'shell_environment_policy={inherit="core",ignore_default_excludes=false}',
    );
  } else {
    arguments_.push("--sandbox", "read-only");
  }

  arguments_.push(
    "--ephemeral",
    "--ignore-user-config",
    "--ignore-rules",
    "-c",
    "features.memories=false",
    "-c",
    "features.hooks=false",
    "-c",
    "features.skip_host_skill_discovery=true",
    "-c",
    "project_doc_max_bytes=0",
    "-c",
    "features.apps=false",
    "-c",
    "features.plugins=false",
    "-c",
    "features.browser_use=false",
    "-c",
    "features.computer_use=false",
    "-c",
    "features.image_generation=false",
    "-c",
    "features.view_image=false",
    "-c",
    "features.multi_agent_v2=false",
    "-c",
    `web_search="${options.run.execution.purpose === "review" && options.run.execution.network === true ? "live" : "disabled"}"`,
  );

  if (
    options.run.execution.purpose === "learning" ||
    options.run.allowedTools?.length === 0
  ) {
    arguments_.push("--disable", "shell_tool");
  }

  if (options.run.model) {
    arguments_.push("--model", options.run.model);
  }

  if (options.run.reasoningEffort) {
    arguments_.push(
      "-c",
      `model_reasoning_effort="${options.run.reasoningEffort}"`,
    );
  }

  if (options.outputSchemaPath) {
    arguments_.push("--output-schema", options.outputSchemaPath);
  }

  return arguments_;
}

export function codexProcessArguments(options: {
  readonly arguments: readonly string[];
  readonly run: EngineRunOptions;
  readonly platform?: NodeJS.Platform;
  readonly temporaryDirectory?: string;
}): readonly string[] {
  if (isCodexEvaluationExecution(options.run)) {
    return options.arguments;
  }

  return evaluationCommand({
    arguments: options.arguments,
    run: options.run,
    platform: options.platform,
    temporaryDirectory: options.temporaryDirectory,
  });
}
