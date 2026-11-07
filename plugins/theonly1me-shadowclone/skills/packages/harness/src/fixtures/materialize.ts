import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { canonicalPath } from "@shadowclone/core";

export type FixtureRepository = {
  readonly name: string;
  readonly files: Readonly<Record<string, string>>;
  readonly specification: string;
  readonly acceptance: Readonly<Record<string, string>>;
  readonly acceptanceCommand: string;
};

export async function materializeFixture(options: {
  readonly fixture: FixtureRepository;
  readonly parent?: string;
  readonly includeAcceptance?: boolean;
}): Promise<string> {
  const parent = options.parent ?? os.tmpdir();

  await mkdir(parent, { recursive: true });

  const root = canonicalPath(
    await mkdtemp(path.join(parent, `${options.fixture.name}-`)),
  );
  const files = options.includeAcceptance
    ? { ...options.fixture.files, ...options.fixture.acceptance }
    : options.fixture.files;

  for (const [relativePath, content] of Object.entries(files)) {
    await Bun.write(path.join(root, relativePath), content);
  }

  return root;
}
