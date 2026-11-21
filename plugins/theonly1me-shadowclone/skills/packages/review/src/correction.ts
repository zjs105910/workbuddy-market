import type { ReviewCandidate } from "./candidates";
import { escapeData, type ReviewPacket, reviewPrompt } from "./packet";
import type { Analysis } from "./types";

export function correctionPrompt(options: {
  readonly skill: string;
  readonly packet: ReviewPacket;
  readonly candidates: readonly ReviewCandidate[];
  readonly previous: Analysis;
  readonly rejections: readonly string[];
}): string {
  return `${reviewPrompt({ skill: options.skill, packet: options.packet, candidates: options.candidates })}

Your previous answer follows, with the problems that code found in it. Return the full corrected answer in the same schema.
For each rejected finding, read the source again and copy the quote exactly, or remove the finding.
Give each candidate id exactly one decision.

<previous_answer>
${escapeData(JSON.stringify(options.previous, null, 1))}
</previous_answer>
<rejections>
${escapeData(options.rejections.map((rejection) => `- ${rejection}`).join("\n"))}
</rejections>`;
}
