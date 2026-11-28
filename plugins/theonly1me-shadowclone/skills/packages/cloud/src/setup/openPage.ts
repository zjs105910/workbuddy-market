export async function openPage(url: string): Promise<boolean> {
  const executable = Bun.which(process.platform === "darwin" ? "open" : "xdg-open");

  if (!executable || !/^https:\/\/github\.com\//.test(url)) {
    return false;
  }

  const child = Bun.spawn([executable, url], { stdout: "ignore", stderr: "ignore" });

  return (await child.exited) === 0;
}

export function pendingPages(
  items: readonly { readonly done: boolean; readonly links: readonly { readonly url: string }[] }[],
): readonly string[] {
  return [
    ...new Set(
      items.filter((item) => !item.done).flatMap((item) => item.links.map((link) => link.url)),
    ),
  ].slice(0, 3);
}
