import { fingerprint } from "@shadowclone/core";
import { bannedTitleWords, buildNamePrompt, buildNameSkills, type NamedSkill } from "./buildNamePrompt";
import { buildNameSchema, type BuildName, type BuildNameResult } from "./buildNameProtocol";
import { generationEngine, type GenerationEngine } from "./generationEngine";
import { generationDestination, structuredCall } from "./structuredCall";
import type { BuildContext } from "@shadowclone/environment";

export const buildNameLimits = { maximumCalls: 1, timeoutMilliseconds: 30_000, maximumCostUsd: 0.05 } as const;

function withoutDashes(text: string): string {
  return text.replace(/\s*[\u2013\u2014]\s*/g, ", ");
}

function checkedName(options: { readonly name: BuildName; readonly skills: readonly NamedSkill[] }): BuildName {
  const titles = new Map(options.skills.map((skill) => [skill.title.trim().toLowerCase(), skill.title]));
  const expected = Math.min(3, options.skills.length);

  if (options.name.abilities.length !== expected) {
    throw new Error(`The model returned ${options.name.abilities.length} abilities instead of ${expected}`);
  }

  const banned = bannedTitleWords.find((word) => options.name.title.toLowerCase().includes(word.toLowerCase()));

  if (banned) throw new Error(`The model used the banned title word "${banned}"`);

  return {
    title: withoutDashes(options.name.title),
    profile: withoutDashes(options.name.profile),
    tradeoff: withoutDashes(options.name.tradeoff),
    abilities: options.name.abilities.map((ability) => {
      const skill = titles.get(ability.skill.trim().toLowerCase());

      if (!skill) throw new Error(`The model named a skill that is not equipped: ${ability.skill.slice(0, 80)}`);

      return { skill, text: withoutDashes(ability.text) };
    }),
  };
}

export function createBuildNames(
  context: BuildContext & { readonly engine?: GenerationEngine; readonly random?: () => number },
) {
  const cache = new Map<string, BuildNameResult>();
  let current: AbortController | null = null;

  return async (request: { readonly input: unknown; readonly signal?: AbortSignal }): Promise<BuildNameResult> => {
    const skills = await buildNameSkills({ ...context, input: request.input });

    if (skills.length === 0) throw new Error("Equip a skill before naming your build");

    const connection = await generationEngine({ ...context, tier: "fast" });
    const destination = generationDestination(connection);
    const key = fingerprint(JSON.stringify({ engine: connection.engine, model: connection.model ?? null, skills }));
    const cached = cache.get(key);

    if (cached) return cached;

    current?.abort(new Error("A newer selection replaced this request"));

    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, ...(request.signal ? [request.signal] : [])]);

    current = controller;

    try {
      const prompt = buildNamePrompt({ skills, random: context.random ?? Math.random });

      if (Buffer.byteLength(prompt) > 12_000) throw new Error("This build is too large to name");

      const result = await structuredCall({
        connection,
        prompt,
        schema: buildNameSchema,
        limits: buildNameLimits,
        cwd: context.cwd,
        signal,
        task: "name the build",
      });
      const name = checkedName({ name: result, skills });
      const output = { name, destination };

      if (cache.size >= 64) cache.clear();

      cache.set(key, output);

      return output;
    } finally {
      if (current === controller) current = null;
    }
  };
}
