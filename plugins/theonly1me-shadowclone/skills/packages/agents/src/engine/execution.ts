import type { EngineRunOptions } from "./types";

export const reviewTools = ["Read", "Grep", "Glob", "Agent"] as const;
export const reviewNetworkTools = ["WebFetch", "WebSearch"] as const;

function validateReviewExecution(options: EngineRunOptions): void {
  const allowedTools = options.allowedTools ?? [];
  const network = options.execution.purpose === "review" && options.execution.network === true;
  const permitted: readonly string[] = network ? [...reviewTools, ...reviewNetworkTools] : reviewTools;
  const onlyPermittedTools = allowedTools.every((tool) => permitted.includes(tool));

  if (allowedTools.length === 0 || !onlyPermittedTools) {
    throw new Error(`Review runs allow only ${permitted.join(", ")}`);
  }

  if (options.systemPromptFile !== undefined) {
    throw new Error("Review cannot load a system prompt file");
  }

  if (options.permissionMode !== "dontAsk") {
    throw new Error("Review requires the dontAsk permission mode");
  }
}

export function validateEngineExecution(options: EngineRunOptions): void {
  if (options.execution.purpose === "review") {
    validateReviewExecution(options);
    return;
  }

  if (options.execution.purpose !== "learning") {
    return;
  }

  if (options.systemPromptFile !== undefined) {
    throw new Error("Learning cannot load a system prompt file");
  }

  if (options.allowedTools && options.allowedTools.length > 0) {
    throw new Error("Learning cannot enable provider tools");
  }

  if (
    options.permissionMode !== undefined &&
    options.permissionMode !== "dontAsk"
  ) {
    throw new Error("Learning requires the dontAsk permission mode");
  }
}
