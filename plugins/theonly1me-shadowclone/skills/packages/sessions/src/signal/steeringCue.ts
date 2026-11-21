const durableSteeringPatterns: readonly RegExp[] = [
  /\b(always|never|avoid|prefer|instead|rather than|from now on|going forward|next time|make sure|remember)\b/i,
  /\b(don't|do not|stop|please use|we use|i want|i'd like|keep it)\b/i,
  /^\s*(no|nope|wrong|actually|revert|undo|that's not|thats not)\b/i,
];

export function hasDurableSteeringCue(text: string): boolean {
  return durableSteeringPatterns.some((pattern) => pattern.test(text));
}
