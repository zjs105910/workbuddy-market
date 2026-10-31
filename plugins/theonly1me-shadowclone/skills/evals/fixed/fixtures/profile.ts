import { keyItemSchema } from "../../native/study/schema";

export const profile = [
  ["comments", "Add no code comments unless the current request explicitly asks for one."],
  ["types", "Use explicit types without any, non-null assertions, or type assertions."],
  ["parameters", "New functions with two or more inputs take one options object. Preserve existing public APIs."],
  ["git", "Do not create commits or change branches unless the current request explicitly authorizes it."],
  ["brevity", "Keep final answers at most 80 words, unless the current request specifies a different length."],
].map(([id, statement]) => keyItemSchema.parse({ id, statement, group: "personal", evidence: "Independently authored synthetic profile, version 1." }));

export const profileText = `${profile.map((item) => `- ${item.statement}`).join("\n")}\n`;

export const repositoryInstructions = "# Repository requirements\n\nUse Bun and TypeScript. Preserve existing public exports. Do not add dependencies. Run relevant tests when changing code. Current task instructions override personal defaults; repository requirements remain authoritative.\n";
