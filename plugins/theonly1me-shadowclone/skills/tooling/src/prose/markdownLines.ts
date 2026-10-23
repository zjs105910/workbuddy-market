export type MarkdownLine = {
  readonly number: number;
  readonly text: string;
  readonly inFence: boolean;
};

const fencePattern = /^\s*(`{3,}|~{3,})/;

export function markdownLines(text: string): readonly MarkdownLine[] {
  const lines: MarkdownLine[] = [];
  let fence: string | null = null;

  for (const [index, line] of text.split("\n").entries()) {
    const marker = fencePattern.exec(line)?.[1] ?? null;

    if (marker !== null) {
      fence = fence === null ? marker : marker.startsWith(fence) ? null : fence;
      lines.push({ number: index + 1, text: line, inFence: true });
      continue;
    }

    lines.push({ number: index + 1, text: line, inFence: fence !== null });
  }

  return lines;
}
