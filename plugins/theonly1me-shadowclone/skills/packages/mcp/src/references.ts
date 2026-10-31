import { z } from "zod";
import type { ProjectPaths } from "@shadowclone/core";
import { recallReferences } from "@shadowclone/profile";
import type { GitRemoteReader } from "@shadowclone/sessions";

export const referenceTools = [
  {
    name: "shadowclone_recall",
    description:
      "Retrieve full, scoped engineering reference records from the local Shadowclone library.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", minLength: 1, maxLength: 1_000 },
        limit: { type: "integer", minimum: 1, maximum: 10, default: 3 },
      },
      required: ["query"],
      additionalProperties: false,
    },
  },
] as const;

const callSchema = z.object({
  name: z.string(),
  arguments: z.unknown().optional(),
});
const recallSchema = z.strictObject({
  query: z.string().trim().min(1).max(1_000),
  limit: z.number().int().min(1).max(10).optional().default(3),
});

export async function runReferenceTool(options: {
  readonly params: unknown;
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<{
  readonly content: readonly { readonly type: "text"; readonly text: string }[];
  readonly isError: boolean;
} | null> {
  const call = callSchema.safeParse(options.params);

  if (!call.success || call.data.name !== "shadowclone_recall") {
    return null;
  }

  const parameters = recallSchema.safeParse(call.data.arguments);

  if (!parameters.success) {
    return {
      content: [{ type: "text", text: "Invalid recall parameters." }],
      isError: true,
    };
  }

  try {
    const result = await recallReferences({ ...options, ...parameters.data });
    const text =
      result.records.length === 0
        ? "No matching references found."
        : result.records.join("\n");

    return { content: [{ type: "text", text }], isError: false };
  } catch {
    return {
      content: [
        {
          type: "text",
          text: "Reference recall failed. Check policy and local profile files.",
        },
      ],
      isError: true,
    };
  }
}
