import { fingerprint } from "@shadowclone/core";
import type { DiscoveredSkill } from "@shadowclone/skills";

export type SkillPair = readonly [DiscoveredSkill, DiscoveredSkill];

export function shareSkillScope(pair: SkillPair): boolean {
  const [left, right] = pair;
  return left.id !== right.id && (
    left.root.scope === "global" || right.root.scope === "global" || left.root.cwd === right.root.cwd
  );
}

export function comparisonFingerprint(pair: SkillPair): string {
  return fingerprint(JSON.stringify({ version: 1, skills: pair.map(skillIdentity) }));
}

function skillIdentity(skill: DiscoveredSkill) {
  return { id: skill.id, fingerprint: skill.fingerprint, scope: skill.root.scope, directory: skill.root.cwd };
}

export function catalogEntry(skill: DiscoveredSkill) {
  return {
    name: skill.name,
    description: skill.description,
    scope: skill.root.scope,
    owner: skill.root.owner,
  };
}

export type CatalogBatch = {
  readonly fingerprint: string;
  readonly left: readonly DiscoveredSkill[];
  readonly right: readonly DiscoveredSkill[];
};

export function libraryCatalogBatches(skills: readonly DiscoveredSkill[]): readonly CatalogBatch[] {
  const chunks: DiscoveredSkill[][] = [];
  let chunk: DiscoveredSkill[] = [];
  let bytes = 0;

  for (const skill of skills) {
    const size = Buffer.byteLength(JSON.stringify(catalogEntry(skill)));

    if (chunk.length > 0 && (chunk.length === 32 || bytes + size > 30_000)) {
      chunks.push(chunk);
      chunk = [];
      bytes = 0;
    }

    chunk.push(skill);
    bytes += size;
  }

  if (chunk.length > 0) chunks.push(chunk);

  const batches: CatalogBatch[] = [];

  for (const [position, left] of chunks.entries()) {
    for (const right of chunks.slice(position)) {
      if (!left.some((first) => right.some((second) => shareSkillScope([first, second])))) continue;

      batches.push({
        fingerprint: fingerprint(JSON.stringify({ version: 1, left: left.map(skillIdentity), right: right.map(skillIdentity) })),
        left,
        right,
      });
    }
  }

  return batches;
}

export function resolveCatalogPair(options: {
  readonly batch: CatalogBatch;
  readonly left: string;
  readonly right: string;
}): SkillPair {
  const left = options.batch.left.find(({ id }) => id === options.left);
  const right = options.batch.right.find(({ id }) => id === options.right);

  if (!left || !right || !shareSkillScope([left, right])) {
    throw new Error("Library review selected an unknown or unrelated skill pair");
  }

  return left.id.localeCompare(right.id) < 0 ? [left, right] : [right, left];
}
