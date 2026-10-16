export function dismissOnBackdrop(modal: HTMLDialogElement): void {
  let pressedOutside = false;

  const outside = (event: PointerEvent | MouseEvent): boolean => {
    const bounds = modal.getBoundingClientRect();

    return (
      event.target === modal &&
      (event.clientX < bounds.left ||
        event.clientX > bounds.right ||
        event.clientY < bounds.top ||
        event.clientY > bounds.bottom)
    );
  };

  modal.addEventListener("pointerdown", (event) => {
    pressedOutside = outside(event);
  });

  modal.addEventListener("click", (event) => {
    if (pressedOutside && outside(event)) {
      modal.close();
    }

    pressedOutside = false;
  });
}
