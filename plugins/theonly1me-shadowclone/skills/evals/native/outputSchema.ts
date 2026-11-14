import { z } from "zod";

export function nativeOutputSchema(schema: z.ZodType): unknown {
  return Object.fromEntries(Object.entries(z.toJSONSchema(schema, { target: "draft-7" }))
    .filter(([key]) => key !== "$schema"));
}
