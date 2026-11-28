import type { LearningRecord } from "@shadowclone/environment";

const hiddenCharacters = new Set([
  0x200b, 0x200c, 0x200d, 0x2060, 0xfeff, 0x202a, 0x202b, 0x202c, 0x202d, 0x202e, 0x2066, 0x2067,
  0x2068, 0x2069,
]);

const instructionPatterns: readonly { readonly pattern: RegExp; readonly reason: string }[] = [
  {
    pattern:
      /\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|any|other|system|developer)\b[^.\n]{0,20}\b(?:instructions?|rules?|guidance|prompts?|messages?)\b/i,
    reason: "tells the agent to ignore other instructions",
  },
  {
    pattern:
      /\byou are now\b|\bnew instructions?\s*:|\bsystem prompt\b|\bdeveloper message\b|<\/?\s*(?:system|assistant|instructions?)\s*>|\[\/?INST\]|<\|im_(?:start|end)\|>/i,
    reason: "imitates a system or role message",
  },
  {
    pattern: /\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:bash|sh|zsh|python3?|node)\b/i,
    reason: "pipes a download into a shell",
  },
  {
    pattern:
      /\b(?:send|post|upload|exfiltrate|forward|paste)\b[^.\n]{0,60}\b(?:secrets?|tokens?|credentials?|passwords?|api keys?|private keys?|ssh keys?|environment variables)\b/i,
    reason: "asks to send secrets or credentials",
  },
];

function hasHiddenCharacters(text: string): boolean {
  return [...text].some((character) => {
    const code = character.codePointAt(0) ?? 0;

    return hiddenCharacters.has(code) || (code >= 0xe0000 && code <= 0xe007f);
  });
}

function hasEncodedBlob(text: string): boolean {
  const blob = /[A-Za-z0-9+/]{60,}={0,2}/.exec(text)?.[0] ?? "";

  return /[A-Z]/.test(blob) && /[a-z]/.test(blob) && /\d/.test(blob);
}

export function instructionShapedReasons(text: string): readonly string[] {
  return [
    ...instructionPatterns.filter(({ pattern }) => pattern.test(text)).map(({ reason }) => reason),
    ...(hasHiddenCharacters(text) ? ["contains hidden or direction-changing characters"] : []),
    ...(hasEncodedBlob(text) ? ["contains a long encoded string"] : []),
  ];
}

export function heldLearningReason(record: LearningRecord): string | null {
  if (record.rule.source !== "mined") {
    return null;
  }

  const reasons = [
    ...new Set(
      [record.rule.title, record.rule.body, ...record.rule.appliesWhen].flatMap(
        instructionShapedReasons,
      ),
    ),
  ];

  return reasons.length === 0
    ? null
    : `Held for review because its text ${reasons.join(", and ")}. Rewrite it with shadowclone learning replace, or retire it with shadowclone learning retire.`;
}
