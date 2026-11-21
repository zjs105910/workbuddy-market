import path from "node:path";
import { z } from "zod";
import { fingerprint } from "../../shared/structured";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { digestSchema, identitySchema } from "./schema";

const sourceSchema = z.strictObject({
  preparationFile: z.string(),
  preparationFingerprint: digestSchema,
  product: identitySchema,
  files: z.array(z.strictObject({ path: z.string(), fingerprint: digestSchema })),
  fingerprint: digestSchema,
});

export const preparationSourceFiles = [
  "evals/fixed/workflow/learner.ts",
  "evals/shared/accounting.ts",
  "evals/fixed/reusable/corpus.ts",
  "evals/fixed/reusable/corpusScope.ts",
  "evals/fixed/reusable/environments.ts",
  "evals/fixed/reusable/preparation.ts",
  "evals/fixed/reusable/learning.ts",
  "evals/fixed/reusable/learningLimits.ts",
  "evals/fixed/reusable/learningSource.ts",
  "evals/fixed/reusable/reuse.ts",
  "evals/fixed/reusable/guidance.ts",
  "package.json",
  "bun.lock",
];

export async function learningSourceFiles(repository: string) {
  const files: { path: string; fingerprint: string }[] = [];
  for await (const file of new Bun.Glob("src/**/*.ts").scan({ cwd: repository, onlyFiles: true })) {
    if (
      file.endsWith(".test.ts") ||
      file.startsWith("evals/") ||
      file === "src/cli/reusableEval.ts"
    )
      continue;
    files.push({
      path: file,
      fingerprint: Bun.CryptoHasher.hash(
        "sha256",
        await Bun.file(path.join(repository, file)).bytes(),
        "hex",
      ),
    });
  }
  for (const file of preparationSourceFiles) {
    files.push({
      path: file,
      fingerprint: Bun.CryptoHasher.hash(
        "sha256",
        await Bun.file(path.join(repository, file)).bytes(),
        "hex",
      ),
    });
  }
  return files.toSorted((left, right) => left.path.localeCompare(right.path));
}

export async function writeLearningSource(options: {
  preparationFile: string;
  preparationFingerprint: string;
  product: z.infer<typeof identitySchema>;
  repository: string;
}) {
  const files = await learningSourceFiles(options.repository);
  const sourceFile = path.join(path.dirname(options.preparationFile), "learning-source.json");
  await writeFrozenArtifact({
    file: sourceFile,
    value: sourceSchema.parse({
      preparationFile: path.resolve(options.preparationFile),
      preparationFingerprint: options.preparationFingerprint,
      product: options.product,
      files,
      fingerprint: fingerprint(files),
    }),
  });
  return sourceFile;
}

export async function requireUnchangedLearningSource(options: {
  sourceFile: string;
  repository: string;
}) {
  const source = sourceSchema.parse(await readFrozenArtifact(options.sourceFile));
  const current = await learningSourceFiles(options.repository);
  if (
    fingerprint(source.files) !== source.fingerprint ||
    fingerprint(current) !== source.fingerprint
  )
    throw new Error(
      "Learning implementation, fixture setup, corpus, or runtime changed; cached preparations cannot be reused.",
    );
  return source;
}
