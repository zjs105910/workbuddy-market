export function makeTargets(text: string): readonly string[] {
  const targets = [
    ...text.matchAll(/^([A-Za-z0-9][A-Za-z0-9_.-]*)\s*:(?!=)/gm),
  ].map((match) => match[1] ?? "");

  return [
    ...new Set(
      targets.filter((target) => target.length > 0 && !target.startsWith(".")),
    ),
  ];
}
