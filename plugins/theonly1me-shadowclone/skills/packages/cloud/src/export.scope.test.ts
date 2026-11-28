import { expect, test } from "bun:test";
import path from "node:path";
import { readEnvironment, writeEnvironment } from "@shadowclone/environment";
import { normalizeRemoteRepository } from "@shadowclone/sessions";
import { exportGuidance } from "./export";
import { guidanceFixture } from "./fixtures";

test("guidance for another remote stays excluded even when its recorded directory matches", async () => {
  const fixture = await guidanceFixture();

  try {
    const state = await readEnvironment(fixture.paths);
    const foreign = normalizeRemoteRepository("https://github.com/other/project.git");

    if (!state || !foreign?.profileFileName) {
      throw new Error("The synthetic environment must have a known origin.");
    }

    const scope = `${foreign.origin.directoryName}/${foreign.profileFileName}`;
    const filePath = path.join(fixture.root, "foreign", "foreign-rule", "SKILL.md");

    await Bun.write(
      filePath,
      "---\nname: foreign-rule\ndescription: Foreign guidance.\n---\n\nUse another team's policy.\n",
    );
    await writeEnvironment({
      paths: fixture.paths,
      state: {
        ...state,
        repositories: [
          {
            directory: fixture.cwd,
            originDirectory: foreign.origin.directoryName,
            repositoryName: foreign.profileFileName,
          },
        ],
        artifacts: [
          ...state.artifacts,
          {
            filePath,
            fingerprint: "synthetic-foreign",
            original: null,
            kind: "skill",
            scope,
            name: "foreign-rule",
            description: "Foreign guidance.",
            learningKeys: [],
          },
        ],
        facts: [{ scope, text: "Foreign-only marker.", learningKeys: [] }],
      },
    });

    const delivery = await exportGuidance({ ...fixture, skills: ["shadowclone-work"] });

    expect(delivery.native).not.toContain("Foreign-only marker");
    expect(delivery.files.some((file) => file.path.includes("foreign-rule"))).toBeFalse();
    await expect(
      exportGuidance({ ...fixture, skills: ["shadowclone-work", "foreign-rule"] }),
    ).rejects.toThrow("not available");
  } finally {
    await fixture.cleanup();
  }
});
