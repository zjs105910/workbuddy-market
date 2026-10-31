import { parseSkillDocument } from "@shadowclone/skills";

export function generatedSkillBody(options: {
  readonly text: string;
  readonly name: string;
}): string {
  const text = options.text.trimStart();

  if (!text.startsWith("---\n") && !text.startsWith("---\r\n")) {
    return options.text;
  }

  const document = parseSkillDocument(text);

  if (document.metadata.name !== options.name) {
    throw new Error("Generated skill name does not match its target");
  }

  const body = document.body.trimStart();

  if (body.startsWith("---\n") || body.startsWith("---\r\n")) {
    throw new Error("Repeated generated metadata requires review");
  }

  if (Object.keys(document.metadata).some((key) => key !== "name" && key !== "description")) {
    throw new Error("Generated invocation settings require review");
  }

  return document.body;
}
