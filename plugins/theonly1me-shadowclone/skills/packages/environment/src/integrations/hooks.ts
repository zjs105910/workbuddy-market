import path from "node:path";
import { z } from "zod";
import { canonicalPath, projectPaths, readEffectiveConfig } from "@shadowclone/core";
import { compileContext, sessionStartProjection } from "./compile";
import { readIntegrations, saveIntegration } from "./state";
import type { Integration, IntegrationOptions } from "./types";
import { bindNativeSessionOrigin, nativeBindingTimestamp } from "./bindings";
import { readEnvironment } from "../environment/store";
import { learningSessionKey } from "./sessionKey";

const inputSchema = z
  .object({
    cwd: z.string().optional(),
    workspace_roots: z.array(z.string()).optional(),
    workspacePaths: z.array(z.string()).optional(),
    session_id: z.string().optional(),
    sessionId: z.string().optional(),
    conversationId: z.string().optional(),
    conversation_id: z.string().optional(),
    hook_event_name: z.string().optional(),
  })
  .passthrough();
type NativeInput = z.infer<typeof inputSchema>;

function parseInput(input: string): NativeInput {
  try {
    return inputSchema.parse(JSON.parse(input || "{}"));
  } catch {
    throw new Error("Invalid native hook input");
  }
}

function nativeSessionId(input: NativeInput): string | null {
  return (
    input.session_id ??
    input.sessionId ??
    input.conversationId ??
    input.conversation_id ??
    null
  );
}

function activeIntegration(options: {
  readonly integration: Integration;
  readonly integrations: readonly Integration[];
  readonly cwd: string;
}): boolean {
  const local = options.integrations
    .filter(
      (entry) =>
        entry.agent === options.integration.agent &&
        entry.scope === "repository" &&
        (options.cwd === entry.directory ||
          options.cwd.startsWith(`${entry.directory}${path.sep}`)),
    )
    .sort((left, right) => right.directory.length - left.directory.length)[0];

  return options.integration.scope === "repository"
    ? local?.id === options.integration.id
    : local === undefined;
}

export async function nativeSessionStart(
  options: IntegrationOptions & {
    readonly id: string;
    readonly input: string;
  },
): Promise<Readonly<Record<string, unknown>>> {
  const paths = options.paths ?? projectPaths;
  const integrations = await readIntegrations(paths);
  const integration = integrations.find((entry) => entry.id === options.id);

  if (!integration) {
    return {};
  }

  const input = parseInput(options.input);
  const cwd = canonicalPath(
    input.cwd ??
      input.workspace_roots?.[0] ??
      input.workspacePaths?.[0] ??
      process.cwd(),
  );

  if (!activeIntegration({ integration, integrations, cwd })) {
    return {};
  }

  const environment = await readEnvironment(paths);
  const scopedDelivery = environment?.phase === "active" &&
    (integration.agent === "claude-code" || integration.agent === "codex" || integration.agent === "pi");
  const profile = await compileContext({
    ...options,
    paths,
    cwd,
    audience: input.hook_event_name === "SubagentStart" ? "subagent" : "main",
    ...(scopedDelivery ? { scope: integration.scope === "global" ? "scoped" as const : "global" as const } : {}),
    ...sessionStartProjection,
  });

  if (profile === null) {
    return {};
  }

  const sessionId = nativeSessionId(input);

  if (sessionId !== null) {
    await bindNativeSessionOrigin({
      ...options,
      paths,
      integration,
      sessionId,
      cwd,
      timestamp: nativeBindingTimestamp(input.timestamp),
    });
  }

  if (scopedDelivery && integration.scope === "repository") {
    return {};
  }

  if (profile.length === 0) {
    return {};
  }

  const additionalContext = profile;

  await saveIntegration({
    paths,
    integration: { ...integration, deliveredAt: Date.now() },
  });

  if (integration.agent === "pi") return { additionalContext };

  if (integration.agent === "cursor") {
    return { additional_context: additionalContext };
  }

  if (integration.agent === "antigravity") {
    return {
      decision: "allow",
      hookSpecificOutput: {
        hookEventName: "PreInvocation",
        ephemeralMessage: additionalContext,
      },
    };
  }

  return {
    hookSpecificOutput: {
      hookEventName:
        integration.agent === "claude-code"
          ? (input.hook_event_name ?? "SessionStart")
          : "SessionStart",
      additionalContext,
    },
  };
}

export async function nativeSessionEnd(
  options: IntegrationOptions & {
    readonly id: string;
    readonly input: string;
  },
): Promise<string | null> {
  const paths = options.paths ?? projectPaths;
  const integration = (await readIntegrations(paths)).find(
    (entry) => entry.id === options.id,
  );

  if (!integration) {
    return null;
  }

  const input = parseInput(options.input);
  if (integration.agent === "pi") {
    const integrations = await readIntegrations(paths);
    if (!activeIntegration({ integration, integrations, cwd: canonicalPath(input.cwd ?? process.cwd()) })) return null;
    const { config } = await readEffectiveConfig({ configPath: options.configPath ?? paths.configFile,
      managedConfigPath: options.managedConfigPath === undefined ? paths.managedConfigFile : options.managedConfigPath });
    if (!config.sources.pi) return null;
  }
  const nativeId = nativeSessionId(input);

  if (!nativeId) {
    return null;
  }

  return learningSessionKey({
    agent: integration.agent,
    nativeSessionId: nativeId,
  });
}
