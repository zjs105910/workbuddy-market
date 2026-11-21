import {
  skillDraftResultSchema,
  skillDraftReviewSchema,
} from "../skillDraftProtocol";
import { request } from "./api";
import { element, input, textarea } from "./dom";
import { showGenerationReview } from "./generationDialog";

export function customStatus(message: string): void {
  element("custom-status").textContent = message;
}

async function reviewSkillDraft(): Promise<void> {
  const body = textarea("custom-body").value;

  if (!body.trim()) {
    customStatus(
      "Describe what your agent should do, then use AI to shape it into a skill.",
    );
    textarea("custom-body").focus();

    return;
  }

  const review = await request({
    path: "/api/skill/preview",
    schema: skillDraftReviewSchema,
    body: {
      name: input("custom-name").value,
      description: input("custom-description").value,
      body,
    },
  });

  showGenerationReview({
    review,
    title: "Draft your skill with AI.",
    explanation:
      "Only the form fields below are sent. The result fills this form for you to edit; adding and applying it remain your choice.",
    confirm: "Send and draft",
    path: "/api/skill/generate",
    schema: skillDraftResultSchema,
    accept: ({ skill }) => {
      input("custom-name").value = skill.name;
      input("custom-description").value = skill.description;
      textarea("custom-body").value = skill.body;
      customStatus(
        "AI draft ready. Edit the instructions before adding the skill to your build.",
      );
      textarea("custom-body").focus();
    },
  });
}

export function initializeCustomGeneration(): void {
  const button = element("custom-ai");

  if (!(button instanceof HTMLButtonElement)) return;

  button.addEventListener("click", () => {
    if (button.disabled) return;

    button.disabled = true;
    customStatus("Preparing your model request…");

    reviewSkillDraft()
      .catch((error: unknown) => {
        customStatus(
          error instanceof Error
            ? error.message
            : "Could not prepare an AI draft. Your text is unchanged.",
        );
      })
      .finally(() => {
        button.disabled = false;

        if (
          element("custom-status").textContent ===
          "Preparing your model request…"
        ) {
          customStatus("");
        }
      });
  });
}
