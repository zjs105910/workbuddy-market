import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fingerprint } from "../../shared/structured";
import { writeFrozenArtifact } from "../workflow/preparation";
import {
  learningSourceFiles,
  requireUnchangedLearningSource,
  preparationSourceFiles,
  writeLearningSource,
} from "./learningSource";

test("cached preparation provenance permits evaluator repair and rejects changed learning implementation or corpus", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-learning-origin-"));
  try {
    const repository = path.join(directory, "repository");
    const paths = ["src/engine/native/index.ts", ...preparationSourceFiles];
    for (const relative of paths) {
      const file = path.join(repository, relative);
      await mkdir(path.dirname(file), { recursive: true });
      await Bun.write(file, "Synthetic unchanged input.\n");
    }
    const files = await learningSourceFiles(repository);
    const sourceFile = path.join(directory, "learning-source.json");
    expect(
      await writeLearningSource({
        preparationFile: path.join(directory, "preparation.json"),
        repository,
        preparationFingerprint: "0".repeat(64),
        product: { commit: "a".repeat(40), tree: "0".repeat(64), branch: "fixture" },
      }),
    ).toBe(sourceFile);
    await expect(requireUnchangedLearningSource({ sourceFile, repository })).resolves.toMatchObject(
      { fingerprint: fingerprint(files) },
    );
    await Bun.write(
      path.join(repository, "evals/fixed/reusable/grading.ts"),
      "Synthetic evaluator repair.\n",
    );
    await expect(requireUnchangedLearningSource({ sourceFile, repository })).resolves.toMatchObject(
      { fingerprint: fingerprint(files) },
    );
    for (const relative of [
      "src/engine/native/index.ts",
      "evals/fixed/reusable/corpus.ts",
      "evals/fixed/reusable/environments.ts",
      "evals/fixed/reusable/corpusScope.ts",
      "evals/fixed/reusable/learning.ts",
    ]) {
      const file = path.join(repository, relative);
      await Bun.write(file, "Changed model input.\n");
      await expect(requireUnchangedLearningSource({ sourceFile, repository })).rejects.toThrow(
        "cannot be reused",
      );
      await Bun.write(file, "Synthetic unchanged input.\n");
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});

test("older seals without fixture setup cannot qualify corrected preparations", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "v3-old-source-"));
  try {
    for (const relative of preparationSourceFiles) {
      const file = path.join(directory, relative);
      await mkdir(path.dirname(file), { recursive: true });
      await Bun.write(file, "Synthetic source.\n");
    }
    const files = (await learningSourceFiles(directory)).filter(
      (file) => file.path !== "evals/fixed/reusable/corpusScope.ts",
    );
    const sourceFile = path.join(directory, "old-source.json");
    await writeFrozenArtifact({
      file: sourceFile,
      value: {
        preparationFile: path.join(directory, "preparation.json"),
        preparationFingerprint: "0".repeat(64),
        product: { commit: "a".repeat(40), tree: "0".repeat(64), branch: "fixture" },
        files,
        fingerprint: fingerprint(files),
      },
    });
    await expect(
      requireUnchangedLearningSource({ sourceFile, repository: directory }),
    ).rejects.toThrow("cannot be reused");
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
