import type { Stack, StackContext } from "../types";

function configures(options: {
  readonly context: StackContext;
  readonly files: readonly string[];
  readonly sections: readonly string[];
}): boolean {
  const { context } = options;

  if (options.files.some((file) => context.exists(file))) {
    return true;
  }

  return ["pyproject.toml", "setup.cfg"].some(
    (file) => context.exists(file) && options.sections.some((section) => context.read(file).includes(section)),
  );
}

function changedPython(context: StackContext): readonly string[] {
  return context.changedFiles.filter((file) => /\.pyi?$/.test(file) && context.exists(file));
}

export const pythonStack: Stack = {
  id: "python",
  sources: /\.(?:pyi?|toml|cfg|ini)$|(?:^|\/)requirements[^/]*\.txt$/,
  detect: (context) =>
    ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"].some((file) => context.exists(file)),
  install: () => null,
  commands: [
    {
      tool: "ruff",
      scope: "changed-lines",
      parser: "colon",
      command: (context) => {
        const files = changedPython(context);
        const configured = configures({ context, files: ["ruff.toml", ".ruff.toml"], sections: ["[tool.ruff"] });

        return configured && files.length > 0 ? ["ruff", "check", "--output-format", "concise", ...files] : null;
      },
    },
    {
      tool: "mypy",
      scope: "new-in-head",
      parser: "colon",
      command: (context) =>
        configures({ context, files: ["mypy.ini", ".mypy.ini"], sections: ["[tool.mypy", "[mypy]"] })
          ? ["mypy", "--ignore-missing-imports", "--no-error-summary", "--no-pretty", "."]
          : null,
    },
    {
      tool: "pyright",
      scope: "new-in-head",
      parser: "pyright",
      command: (context) =>
        configures({ context, files: ["pyrightconfig.json"], sections: ["[tool.pyright"] }) ? ["pyright"] : null,
    },
  ],
};
