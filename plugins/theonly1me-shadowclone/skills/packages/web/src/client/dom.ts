export function element(id: string): HTMLElement {
  const found = document.getElementById(id);

  if (found === null) {
    throw new Error("The editor is missing a required control");
  }

  return found;
}

export function svg(id: string): SVGSVGElement {
  const found = document.querySelector(`#${id}`);

  if (!(found instanceof SVGSVGElement)) {
    throw new Error("Expected an SVG canvas");
  }

  return found;
}

export function input(id: string): HTMLInputElement {
  const found = element(id);

  if (!(found instanceof HTMLInputElement)) {
    throw new Error("Expected an input control");
  }

  return found;
}

export function select(id: string): HTMLSelectElement {
  const found = element(id);

  if (!(found instanceof HTMLSelectElement)) {
    throw new Error("Expected a selection control");
  }

  return found;
}

export function textarea(id: string): HTMLTextAreaElement {
  const found = element(id);

  if (!(found instanceof HTMLTextAreaElement)) {
    throw new Error("Expected a text editor");
  }

  return found;
}

export function dialog(id: string): HTMLDialogElement {
  const found = element(id);

  if (!(found instanceof HTMLDialogElement)) {
    throw new Error("Expected an editor dialog");
  }

  return found;
}

export function create<Tag extends keyof HTMLElementTagNameMap>(options: {
  readonly tag: Tag;
  readonly className?: string;
  readonly text?: string;
}): HTMLElementTagNameMap[Tag] {
  const node = document.createElement(options.tag);

  if (options.className) {
    node.className = options.className;
  }

  if (options.text !== undefined) {
    node.textContent = options.text;
  }

  return node;
}

export function notice(options: {
  readonly message: string;
  readonly success?: boolean;
}): void {
  const target = element("notice");

  target.textContent = options.message;
  target.classList.toggle("success", options.success === true);
  target.hidden = options.message.length === 0;
}

export function reportError(error: unknown): void {
  notice({
    message: error instanceof Error ? error.message : "The action failed.",
  });
}
