import { expect, test } from "bun:test";
import product from "@shadowclone/core/product.json";
import { handleMcpRequest } from "./server";
import { preferenceTools } from "./preferences";
import { referenceTools } from "./references";
import { botTools } from "./bot";

test("responds to initialize with protocol version and serverInfo", () => {
  const response = handleMcpRequest({
    request: { id: 1, method: "initialize", params: {} },
    profile: "",
  });

  expect(response).toEqual({
    jsonrpc: "2.0",
    id: 1,
    result: {
      protocolVersion: "2024-11-05",
      capabilities: { tools: {} },
      serverInfo: { name: "shadowclone", version: product.version },
    },
  });
});

test("advertises profile recall and explicit preference operations", () => {
  const response = handleMcpRequest({
    request: { id: 1, method: "tools/list", params: {} },
    profile: "",
  });

  expect(response).toEqual({
    jsonrpc: "2.0",
    id: 1,
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
  });
});

test("returns the scoped profile through the recall tool", () => {
  const response = handleMcpRequest({
    request: {
      id: "call-1",
      method: "tools/call",
      params: { name: "shadowclone_profile", arguments: {} },
    },
    profile: "# Shadowclone profile\n\nUse Bun.",
  });

  expect(response).toEqual({
    jsonrpc: "2.0",
    id: "call-1",
    result: {
      content: [{ type: "text", text: "# Shadowclone profile\n\nUse Bun." }],
      isError: false,
    },
  });
});
