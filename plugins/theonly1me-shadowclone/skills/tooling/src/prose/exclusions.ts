export const proseExclusions = {
  excluded: [
    ".git/**",
    "**/node_modules/**",
    "**/.turbo/**",
    "**/coverage/**",
    "**/dist/**",
    "**/out/**",
    "CHANGELOG.md",
    "skills/**",
    "preferences/**",
    ".agents/**",
    ".claude/skills/**",
    "packages/builds/src/fixtures/**",
    "evals/no-comments/task/**",
    "evals/no-comments/graders/**",
  ],
  kept: [".claude/skills/data-handling/**"],
} as const;
