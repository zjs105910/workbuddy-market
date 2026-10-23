import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";

export const deliveryFileSchema = z.strictObject({
  path: z.string().regex(/^(?!\/)(?!.*(?:^|\/)\.\.(?:\/|$))[A-Za-z0-9_.\/-]+$/),
  content: z.string().regex(/^[A-Za-z0-9+/]*={0,2}$/),
  mode: z.number().int().min(0).max(0o777),
});

export type DeliveryFile = z.infer<typeof deliveryFileSchema>;

export function deliveryFingerprint(files: readonly DeliveryFile[]): string {
  const sorted = [...z.array(deliveryFileSchema).parse(files)].sort((left, right) =>
    left.path.localeCompare(right.path),
  );

  return new Bun.CryptoHasher("sha256").update(JSON.stringify(sorted)).digest("hex");
}

export async function writeDeliveryFiles(options: {
  readonly files: readonly DeliveryFile[];
  readonly destination: string;
}): Promise<void> {
  await mkdir(options.destination, { recursive: true, mode: 0o700 });

  for (const file of z.array(deliveryFileSchema).parse(options.files)) {
    const target = path.join(options.destination, file.path);

    await mkdir(path.dirname(target), { recursive: true, mode: 0o700 });
    await writeFile(target, Buffer.from(file.content, "base64"), { mode: file.mode, flag: "wx" });
  }
}
