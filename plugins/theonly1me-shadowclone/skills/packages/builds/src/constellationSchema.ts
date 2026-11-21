import { z } from "zod";

export const constellationHubSchema = z.strictObject({
  id: z.string(),
  title: z.string(),
  parentId: z.string().nullable(),
});

export const constellationLeafSchema = z.strictObject({
  id: z.string(),
  itemIds: z.array(z.string()).min(1),
  parentId: z.string(),
  relatedHubIds: z.array(z.string()).max(2),
});

export const constellationSchema = z.strictObject({
  hubs: z.array(constellationHubSchema),
  leaves: z.array(constellationLeafSchema),
});

export type Constellation = z.infer<typeof constellationSchema>;
