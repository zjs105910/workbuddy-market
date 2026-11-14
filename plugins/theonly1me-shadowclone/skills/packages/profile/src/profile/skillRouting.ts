export function isSkillRoutingInstruction(body: string): boolean {
  return (
    /\b(?:load|invoke|select|review|inspect)\b[\s\S]*\b(?:skills?|clean-code|scoped-fix)\b/i.test(
      body,
    ) && /\b(?:before|first|when|relevant|required|mandatory)\b/i.test(body)
  );
}

export function assertNotCoveredRouting(options: {
  readonly body: string;
  readonly reason: string;
}): void {
  if (
    options.reason === "skill-covered" &&
    isSkillRoutingInstruction(options.body)
  ) {
    throw new Error(
      "Skill-loading instructions are routing, not duplicate skill bodies; retain the steering or explicitly review its removal",
    );
  }
}
