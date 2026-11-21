import { rm } from "node:fs/promises";
import path from "node:path";
import { buildRuntimeArtifacts, writeRuntimeArtifacts } from "./bundle";

const packageDirectory = path.resolve(import.meta.dir, "..");
const entryPoint = path.join(packageDirectory, "src/main.ts");
const distDirectory = path.join(packageDirectory, "dist");

if (!(await Bun.file(entryPoint).exists())) {
  throw new Error(`${entryPoint} does not exist, so there is nothing to build`);
}

const artifacts = await buildRuntimeArtifacts(entryPoint);

await rm(distDirectory, { recursive: true, force: true });

const outputFile = await writeRuntimeArtifacts({ artifacts, distDirectory });

console.log(
  `${path.relative(process.cwd(), outputFile)} ${(Bun.file(outputFile).size / 1000).toFixed(0)} KB`,
);
