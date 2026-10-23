import { dismissOnBackdrop } from "./dialogDismissal";

export function initializeEditorDialogs(): void {
  const template = document.createElement("template");

  template.innerHTML = `
    <dialog id="review-dialog" aria-labelledby="review-title">
      <div class="dialog-heading">
        <div>
          <p class="eyebrow">READY TO EQUIP</p>
          <h2 id="review-title">Review your changes.</h2>
        </div>
        <button class="close-dialog quiet-button" aria-label="Close review">
          ✕
        </button>
      </div>
      <div id="review-content"></div>
      <div class="dialog-actions">
        <button class="close-dialog quiet-button">Keep editing</button>
        <button id="apply" class="primary-button">Apply build</button>
      </div>
    </dialog>

    <dialog id="custom-dialog" aria-labelledby="custom-title">
      <div class="dialog-heading">
        <h2 id="custom-title">Create a skill.</h2>
        <button
          class="close-dialog quiet-button"
          aria-label="Close skill editor"
        >
          ✕
        </button>
      </div>
      <form id="custom-form">
        <label>
          Skill name
          <input
            id="custom-name"
            pattern="[a-z0-9]+(-[a-z0-9]+)*"
            maxlength="48"
            placeholder="review-with-evidence"
            required
          >
        </label>
        <label>
          When should your agent use it?
          <input
            id="custom-description"
            maxlength="300"
            placeholder="Use when reviewing an implementation."
            required
          >
        </label>
        <label>
          What should your agent do?
          <textarea
            id="custom-body"
            rows="9"
            maxlength="24000"
            placeholder="Describe the decisions, steps, and evidence you expect."
            required
          ></textarea>
        </label>
        <p id="custom-status" class="review-message" role="status"></p>
        <div class="dialog-actions">
          <button id="custom-ai" type="button" class="quiet-button">✦ Use AI</button>
          <button type="submit" class="primary-button">
            Add to your build
          </button>
        </div>
      </form>
    </dialog>
  `;

  document.body.append(template.content);

  for (const modal of document.querySelectorAll("dialog")) {
    dismissOnBackdrop(modal);
  }
}
