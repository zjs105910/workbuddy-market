import type { z } from "zod";
import { request } from "./api";
import { create } from "./dom";
import { dismissOnBackdrop } from "./dialogDismissal";

type GenerationReview = {
  readonly id: string;
  readonly destination: string;
  readonly payload: string;
  readonly limits: string;
};

export function showGenerationReview<Output>(options: {
  readonly review: GenerationReview;
  readonly title: string;
  readonly explanation: string;
  readonly confirm: string;
  readonly path: string;
  readonly schema: z.ZodType<Output>;
  readonly accept: (output: Output) => void;
}): void {
  const modal = create({ tag: "dialog" });
  const heading = create({ tag: "div", className: "dialog-heading" });
  const close = create({ tag: "button", className: "quiet-button", text: "✕" });
  const details = create({ tag: "details", className: "file-change" });
  const actions = create({ tag: "div", className: "dialog-actions" });
  const status = create({ tag: "p", className: "review-message" });
  const cancel = create({
    tag: "button",
    className: "quiet-button",
    text: "Keep editing",
  });
  const generate = create({
    tag: "button",
    className: "primary-button",
    text: options.confirm,
  });
  const controller = new AbortController();

  modal.setAttribute("aria-label", options.title);
  close.setAttribute("aria-label", "Close model request");
  status.setAttribute("role", "status");

  close.addEventListener("click", () => modal.close());
  dismissOnBackdrop(modal);

  heading.append(create({ tag: "h2", text: options.title }), close);

  details.append(
    create({ tag: "summary", text: "Exact payload sent to the model" }),
    create({ tag: "pre", text: options.review.payload }),
  );

  cancel.addEventListener("click", () => modal.close());
  modal.addEventListener("close", () => {
    controller.abort();
    modal.remove();
  });

  async function generateDraft(): Promise<void> {
    if (generate.disabled) return;

    generate.disabled = true;
    generate.textContent = "Generating…";
    cancel.textContent = "Cancel generation";
    status.textContent =
      "Your model is working. You can cancel and keep your original draft.";

    try {
      const output = await request({
        path: options.path,
        schema: options.schema,
        body: { previewId: options.review.id },
        signal: controller.signal,
      });

      if (!controller.signal.aborted) {
        options.accept(output);
        modal.close();
      }
    } catch (error) {
      if (controller.signal.aborted) return;

      status.className = "review-warning";
      status.textContent =
        error instanceof Error
          ? error.message
          : "Generation failed. Your draft is unchanged.";
      generate.textContent = "Request ended";
      cancel.textContent = "Back to editing";
    }
  }

  generate.addEventListener("click", () => {
    generateDraft().catch(() => {
      status.textContent = "Generation failed. Return to editing to try again.";
    });
  });

  actions.append(cancel, generate);
  modal.append(
    heading,
    create({
      tag: "p",
      className: "review-message",
      text: `Destination: ${options.review.destination}`,
    }),
    create({
      tag: "p",
      className: "review-message",
      text: options.review.limits,
    }),
    create({
      tag: "p",
      className: "review-message",
      text: options.explanation,
    }),
    details,
    status,
    actions,
  );

  document.body.append(modal);
  modal.showModal();
}
