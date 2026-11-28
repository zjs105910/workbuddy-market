import { redactSecrets } from "@shadowclone/redact";

const mention = /(^|[^\w`/])@([A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))(?![\w-])/g;
const crossRepositoryReference = /(^|[^\w`/])([\w.-]+\/[\w.-]+#\d+)/g;
const githubThreadUrl = /(^|[^`<(])(https?:\/\/github\.com\/[\w.-]+\/[\w.-]+\/(?:issues|pull|discussions)\/\d+[^\s)`]*)/g;

export function neutralizeText(text: string): string {
  return redactSecrets({ text })
    .replace(githubThreadUrl, "$1`$2`")
    .replace(crossRepositoryReference, "$1`$2`")
    .replace(mention, "$1`@$2`");
}
