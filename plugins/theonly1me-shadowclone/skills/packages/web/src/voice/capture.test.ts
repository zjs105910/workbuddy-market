import { expect, test } from "bun:test";
import { buildFixture } from "@shadowclone/builds/testing";
import { defaultConfig, readConfig, writeConfig } from "@shadowclone/core";
import type { EngineRunOptions } from "@shadowclone/agents";
import { generationResult } from "../fixtures";
import { createVoiceCapture } from "./capture";
import { voiceFilePath } from "./file";
import { fakeGitHub, invented, keptPullRequest, syntheticToken } from "./fixtures";

async function capture(options: { readonly answer?: unknown } = {}) {
  const fixture = await buildFixture();
  const github = fakeGitHub();
  const runs: EngineRunOptions[] = [];

  await writeConfig({ configPath: fixture.paths.configFile, config: defaultConfig });

  const voice = createVoiceCapture({
    ...fixture,
    hostRunner: github.run,
    engine: {
      engine: "claude-code",
      runner: async (run) => {
        runs.push(run);

        return generationResult(options.answer ?? (run.prompt.startsWith("Write samples") ? invented.samples : invented));
      },
    },
  });

  return { fixture, github, runs, voice };
}

test("the wizard asks for consent first, and capture without it reads nothing", async () => {
  const { fixture, github, runs, voice } = await capture();

  expect(await voice.status()).toEqual({
    consent: false,
    allowed: true,
    voiceFile: { path: voiceFilePath(fixture.paths), state: "missing", target: null },
  });
  await expect(voice.capture(new AbortController().signal)).rejects.toThrow("Allow Shadowclone to read your GitHub writing");
  expect(github.calls).toEqual([]);
  expect(runs).toEqual([]);
});

test("consent is saved, and the model sees only filtered and redacted writing", async () => {
  const { fixture, runs, voice } = await capture();

  expect((await voice.consent({ enabled: true })).consent).toBeTrue();
  expect((await readConfig({ configPath: fixture.paths.configFile })).sources["github-writing"]).toBeTrue();

  const result = await voice.capture(new AbortController().signal);

  expect(result).toEqual({ draft: invented, destination: "claude-code using its default model", sourceCount: 5 });
  expect(runs).toHaveLength(1);
  expect(runs[0]?.prompt).toContain(JSON.stringify(keptPullRequest));
  expect(runs[0]?.prompt).not.toContain(syntheticToken);
  expect(runs[0]?.prompt).not.toContain("Add the sync command");
});

test("a draft that copies 8 words from the writing is discarded", async () => {
  const copied = { ...invented, samples: { ...invented.samples, pullRequest: keptPullRequest } };
  const { voice } = await capture({ answer: copied });

  await voice.consent({ enabled: true });

  await expect(voice.capture(new AbortController().signal)).rejects.toThrow("The model copied 8 or more words in a row");
});

test("a sample rewrite after an edit uses the fast model and sends no source text", async () => {
  const { runs, voice } = await capture();

  await voice.consent({ enabled: true });
  await voice.capture(new AbortController().signal);

  const edited = { ...invented.profile, traits: [...invented.profile.traits, "Asks one question at a time"] };
  const rewritten = await voice.rewrite({ profile: edited }, new AbortController().signal);

  expect(rewritten).toEqual({ draft: { profile: edited, samples: invented.samples }, destination: "claude-code using haiku" });
  expect([runs[1]?.model, runs[1]?.reasoningEffort]).toEqual(["haiku", "low"]);
  expect(runs[1]?.prompt).toContain("Asks one question at a time");
  expect(runs[1]?.prompt).not.toContain("cursor");
});

test("saving writes the voice file once and then refuses to overwrite it", async () => {
  const { fixture, voice } = await capture();

  expect(await voice.save(invented)).toEqual({ path: voiceFilePath(fixture.paths) });
  expect(await Bun.file(voiceFilePath(fixture.paths)).text()).toContain("## Invented examples");
  await expect(voice.save(invented)).rejects.toThrow("already exists, so Shadowclone did not change it");
});

test("turning consent off forgets the collected writing", async () => {
  const { voice } = await capture();

  await voice.consent({ enabled: true });
  await voice.capture(new AbortController().signal);
  await voice.consent({ enabled: false });

  await expect(voice.rewrite({ profile: invented.profile }, new AbortController().signal)).rejects.toThrow(
    "Capture your voice before you rewrite the samples",
  );
});
