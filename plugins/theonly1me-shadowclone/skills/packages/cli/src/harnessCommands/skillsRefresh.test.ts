import { expect, test } from "bun:test";
import { harnessInitCommand } from "../harness";
import { emptyEnvironment, readHarnessManifest, writeEnvironment } from "@shadowclone/environment";
import { bunTaskList, harnessTestSetup } from "@shadowclone/harness/testing";

test("refreshing after skills activation preserves explicit repository checks", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules:
      "## Small files\n\nKeep files under 200 lines.\n\n## Comments\n\nWrite zero comments.\n",
  });
  const options = {
    apply: true as const,
    personal: true,
    skills: [],
    enforceClaude: false,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    ask: () => true,
    writeLine: () => undefined,
  };

  await harnessInitCommand(options);

  const before = await readHarnessManifest(setup.root);

  expect(before?.conventions).toContainEqual({
    kind: "file-length",
    maximumLines: 200,
  });

  await writeEnvironment({
    paths: setup.paths,
    state: { ...emptyEnvironment, phase: "active" },
  });
  await harnessInitCommand(options);

  expect((await readHarnessManifest(setup.root))?.conventions).toEqual(
    before?.conventions,
  );
});
