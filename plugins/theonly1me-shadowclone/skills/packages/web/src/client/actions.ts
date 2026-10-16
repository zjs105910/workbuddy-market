import { element, reportError } from "./dom";

let busy = false;

export async function perform(action: () => Promise<void>): Promise<void> {
  if (busy) return;

  busy = true;

  const controls = document.querySelectorAll<
    | HTMLButtonElement
    | HTMLInputElement
    | HTMLSelectElement
    | HTMLTextAreaElement
  >("button, input, select, textarea");
  const previous = Array.from(controls, (control) => ({
    control,
    disabled: control.disabled,
  }));

  for (const { control } of previous) {
    control.disabled = true;
  }

  try {
    await action();
  } finally {
    for (const { control, disabled } of previous) {
      control.disabled = disabled;
    }

    busy = false;
  }
}

export function actionButton(options: {
  readonly id: string;
  readonly action: () => Promise<void>;
}): void {
  element(options.id).addEventListener("click", () =>
    perform(options.action).catch(reportError),
  );
}
