import { create } from "./dom";

export function botField(options: {
  readonly label: string;
  readonly value?: string;
  readonly type?: string;
}) {
  const label = create({ tag: "label", className: "field" });
  const input = create({ tag: "input" });

  input.value = options.value ?? "";
  input.type = options.type ?? "text";
  input.required = true;
  label.append(create({ tag: "span", text: options.label }), input);

  return { label, input };
}

export function botButton(options: {
  readonly text: string;
  readonly action: () => Promise<void>;
  readonly status: HTMLElement;
}) {
  const button = create({
    tag: "button",
    className: "quiet-button bot-actions",
    text: options.text,
  });

  button.type = "button";
  button.addEventListener("click", () => {
    button.disabled = true;
    options.status.textContent = "Working…";

    options
      .action()
      .catch((error: unknown) => {
        options.status.textContent = error instanceof Error ? error.message : "Setup failed.";
      })
      .finally(() => {
        button.disabled = false;
      });
  });

  return button;
}
