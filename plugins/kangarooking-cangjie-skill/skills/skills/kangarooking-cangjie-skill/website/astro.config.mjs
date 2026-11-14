import { defineConfig } from "astro/config";

const repositoryName = process.env.GITHUB_REPOSITORY?.split("/")[1];
const isGitHubPages = Boolean(process.env.GITHUB_ACTIONS && repositoryName);

export default defineConfig({
  site: process.env.SITE_URL ?? "http://localhost:4321",
  base: isGitHubPages ? `/${repositoryName}` : "/",
  output: "static",
  trailingSlash: "never",
});
