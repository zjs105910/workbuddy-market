function targetEndIndex(options: { readonly text: string; readonly from: number }): number {
  const targetEnd = /[\s)#]/g;

  targetEnd.lastIndex = options.from;

  return targetEnd.exec(options.text)?.index ?? options.text.length;
}

export function markdownLinkTargets(text: string): readonly string[] {
  const targets: string[] = [];
  let searchFrom = 0;

  for (;;) {
    const opener = text.indexOf("](", searchFrom);

    if (opener === -1) {
      return targets;
    }

    const targetStart = opener + 2;
    const targetEnd = targetEndIndex({ text, from: targetStart });
    const delimiter = text.charAt(targetEnd);

    if (targetEnd === targetStart) {
      searchFrom = opener + 1;
      continue;
    }

    if (delimiter === ")") {
      targets.push(text.slice(targetStart, targetEnd));
      searchFrom = targetEnd + 1;
      continue;
    }

    if (delimiter !== "#") {
      searchFrom = targetEnd;
      continue;
    }

    const closer = text.indexOf(")", targetEnd);

    if (closer === -1) {
      return targets;
    }

    targets.push(text.slice(targetStart, targetEnd));
    searchFrom = closer + 1;
  }
}
