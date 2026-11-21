export type ConfirmPrompt = (question: string) => boolean | Promise<boolean>;

export function promptConfirmation(question: string): boolean {
  const answer = prompt(`${question} [y/N]`);

  return answer?.trim().toLowerCase() === "y";
}
