export const entropyThresholdBitsPerCharacter = 4.5;

export function shannonEntropy(value: string): number {
  if (value.length === 0) {
    return 0;
  }

  const occurrences = new Map<string, number>();

  for (const character of value) {
    occurrences.set(character, (occurrences.get(character) ?? 0) + 1);
  }

  let entropy = 0;

  for (const count of occurrences.values()) {
    const probability = count / value.length;

    entropy -= probability * Math.log2(probability);
  }

  return entropy;
}
