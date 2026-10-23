import product from "@shadowclone/core/product.json";
import { preferenceTools } from "./preferences";
import { referenceTools } from "./references";
import { botTools } from "./bot";

type JsonRpcId = string | number | null;

export type JsonRpcRequest = {
  readonly id: JsonRpcId;
  readonly method: string;
  readonly params: unknown;
};

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseRequest(value: unknown): JsonRpcRequest | null {
  if (!isRecord(value) || typeof value.method !== "string") {
    return null;
  }

  const id = typeof value.id === "string" || typeof value.id === "number" ? value.id : null;

  return { id, method: value.method, params: value.params };
}

export function handleMcpRequest(options: {
  readonly request: JsonRpcRequest;
  readonly profile: string;
  readonly toolResult?: Readonly<Record<string, unknown>> | null;
}): Readonly<Record<string, unknown>> | null {
  const base = { jsonrpc: "2.0", id: options.request.id };

  if (options.request.method === "initialize") {
    return {
      ...base,
      result: {
        protocolVersion: "2024-11-05",
        capabilities: { tools: {} },
        serverInfo: { name: "shadowclone", version: product.version },
      },
    };
  }

  if (options.request.method === "tools/list") {
    return {
      ...base,
      result: {
        tools: [
          ...preferenceTools,
          ...referenceTools,
          ...botTools,
          {
            name: "shadowclone_context",
            description: "Inspect applicable learned skills and native routing for this repository",
            inputSchema: { type: "object", properties: {} },
          },
          {
            name: "shadowclone_profile",
            description: "Deprecated alias for shadowclone_context",
            inputSchema: { type: "object", properties: {} },
          },
        ],
      },
    };
  }

  if (options.request.method === "tools/call") {
    if (options.toolResult) {
      return { ...base, result: options.toolResult };
    }

    const params = isRecord(options.request.params) ? options.request.params : {};

    if (params.name !== "shadowclone_profile" && params.name !== "shadowclone_context") {
      return {
        ...base,
        error: { code: -32602, message: "Unknown tool" },
      };
    }

    return {
      ...base,
      result: {
        content: [{ type: "text", text: options.profile }],
        isError: false,
      },
    };
  }

  if (options.request.method.startsWith("notifications/")) {
    return null;
  }

  return {
    ...base,
    error: { code: -32601, message: "Method not found" },
  };
}
