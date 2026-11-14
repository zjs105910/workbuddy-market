export async function mapWithConcurrency<Item, Result>(options: {
  readonly items: readonly Item[];
  readonly limit: number;
  readonly run: (item: Item) => Promise<Result>;
}): Promise<readonly Result[]> {
  const outcomes = new Map<number, Result>();
  let nextIndex = 0;

  const workers = Array.from(
    { length: Math.min(options.limit, options.items.length) },
    async () => {
      while (true) {
        const itemIndex = nextIndex;

        nextIndex += 1;

        const item = options.items[itemIndex];

        if (item === undefined) {
          return;
        }

        outcomes.set(itemIndex, await options.run(item));
      }
    },
  );

  await Promise.all(workers);

  return options.items.map((_, itemIndex) => {
    const outcome = outcomes.get(itemIndex);

    if (outcome === undefined) {
      throw new Error("Concurrent work produced no result");
    }

    return outcome;
  });
}
