type MarkdownFence = {
  readonly marker: "`" | "~";
  readonly length: number;
};

function openingFence(line: string): MarkdownFence | null {
  const match = line.match(/^ {0,3}(`{3,}|~{3,})/);
  const marker = match?.[1];

  if (!marker) {
    return null;
  }

  return {
    marker: marker[0] === "`" ? "`" : "~",
    length: marker.length,
  };
}

function closesFence(line: string, fence: MarkdownFence): boolean {
  const trimmed = line.trimStart();

  if (!trimmed.startsWith(fence.marker.repeat(fence.length))) {
    return false;
  }

  return (
    trimmed.slice(fence.length).trim().replaceAll(fence.marker, "").length === 0
  );
}

export function splitProfileBlocks(text: string): readonly string[] {
  const blocks: string[] = [];
  let lines: string[] = [];
  let fence: MarkdownFence | null = null;

  for (const line of text.trim().split("\n")) {
    if (fence === null && line.startsWith("## ") && lines.length > 0) {
      blocks.push(lines.join("\n"));
      lines = [];
    }

    lines.push(line);

    if (fence !== null) {
      if (closesFence(line, fence)) {
        fence = null;
      }
    } else {
      fence = openingFence(line);
    }
  }

  if (lines.length > 0) {
    blocks.push(lines.join("\n"));
  }

  return blocks.filter((block) => block.trim().length > 0);
}
