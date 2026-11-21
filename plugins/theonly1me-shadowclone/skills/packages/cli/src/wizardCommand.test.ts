import { expect, test } from "bun:test";
import { runWizardCommand } from "./wizardCommand";

test("wizard defaults to the browser and --cli selects the terminal", async () => {
  const events: string[] = [];
  const handlers = {
    terminal: async () => {
      events.push("terminal");
    },
    browser: async () => {
      events.push("browser");
    },
  };

  await runWizardCommand({ ...handlers, arguments: [] });
  await runWizardCommand({ ...handlers, arguments: ["--cli"] });
  await runWizardCommand({ ...handlers, arguments: ["--web"] });

  expect(events).toEqual(["browser", "terminal", "browser"]);
});

test("browser scope and URL-only options reach the launcher", async () => {
  const launches: { readonly repository: boolean; readonly open: boolean }[] =
    [];

  await runWizardCommand({
    arguments: ["--repo", "--no-open"],
    browser: async (options) => {
      launches.push(options);
    },
  });

  expect(launches).toEqual([{ repository: true, open: false }]);
});

test("invalid mode combinations fail without opening an interface", async () => {
  let launches = 0;
  const launch = async () => {
    launches += 1;
  };

  for (const arguments_ of [
    ["--cli", "--web"],
    ["--cli", "--repo"],
    ["--cli", "--no-open"],
    ["--unknown"],
  ]) {
    await expect(
      runWizardCommand({
        arguments: arguments_,
        browser: launch,
        terminal: launch,
      }),
    ).rejects.toThrow("Use wizard");
  }

  expect(launches).toBe(0);
});
