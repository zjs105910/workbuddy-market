import { z } from "zod";

export const relativePathSchema = z.string().min(1).refine((value) =>
  !value.startsWith("/") && !value.includes("\\") &&
    value.split("/").every((segment) => segment !== ".." && segment !== "." && segment.toLowerCase() !== ".git" && segment.length > 0),
  "Expected a confined relative path",
);
export const fileSchema = z.strictObject({
  path: relativePathSchema,
  content: z.string(),
  encoding: z.enum(["utf8", "base64"]).default("utf8"),
  mode: z.number().int().min(0).max(511).default(384),
});
export const nativeFileSchema = fileSchema.extend({ root: z.enum(["home", "workspace"]) });
export const commandSchema = z.strictObject({
  arguments: z.array(z.string().min(1)).min(1),
  directory: z.string().default("."),
});

export type NativeFile = z.infer<typeof nativeFileSchema>;
export type FrozenFile = z.infer<typeof fileSchema>;
export type AcceptanceCheck = {
  readonly files: readonly FrozenFile[];
  readonly commands: readonly z.infer<typeof commandSchema>[];
};
