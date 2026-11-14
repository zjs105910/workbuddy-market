import type { ReferenceSearchResult } from "./types";

export function normalized(value: string): string {
  return value
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function matchValue(options: {
  readonly value: string;
  readonly phrase: string;
  readonly tokens: readonly string[];
}): number {
  const value = normalized(options.value);
  const phrase = value.includes(options.phrase) ? 100 : 0;

  return (
    phrase + options.tokens.filter((token) => value.includes(token)).length
  );
}

type SearchRank = {
  readonly matches: readonly number[];
  readonly scope: number;
};

function rank(result: ReferenceSearchResult, query: string): SearchRank {
  const phrase = normalized(query);
  const tokens = [...new Set(phrase.split(" ").filter(Boolean))];
  const record = result.record;

  return {
    matches: [
      normalized(record.key) === phrase ? 1 : 0,
      matchValue({ value: record.key, phrase, tokens }),
      matchValue({ value: record.title, phrase, tokens }),
      matchValue({ value: record.tags.join(" "), phrase, tokens }),
      matchValue({ value: record.summary, phrase, tokens }),
      matchValue({ value: record.body, phrase, tokens }),
    ],
    scope: record.scope === "project" ? 2 : record.scope === "org" ? 1 : 0,
  };
}

export function compareRank(
  left: readonly number[],
  right: readonly number[],
): number {
  for (let index = 0; index < left.length; index += 1) {
    const difference = (right[index] ?? 0) - (left[index] ?? 0);

    if (difference !== 0) {
      return difference;
    }
  }

  return 0;
}

export function searchReferences(options: {
  readonly references: readonly ReferenceSearchResult[];
  readonly query: string;
  readonly limit: number;
}): readonly ReferenceSearchResult[] {
  const query = normalized(options.query);

  if (query.length === 0) {
    return [];
  }

  return options.references
    .map((result) => ({ result, rank: rank(result, query) }))
    .filter((entry) => entry.rank.matches.some((value) => value > 0))
    .sort(
      (left, right) =>
        compareRank(left.rank.matches, right.rank.matches) ||
        right.rank.scope - left.rank.scope ||
        left.result.record.key.localeCompare(right.result.record.key),
    )
    .slice(0, options.limit)
    .map((entry) => entry.result);
}
