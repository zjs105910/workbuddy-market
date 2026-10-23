const generatedPaths: readonly RegExp[] = [
  /(^|\/)(bun\.lockb?|package-lock\.json|npm-shrinkwrap\.json|yarn\.lock|pnpm-lock\.yaml|Cargo\.lock|go\.sum|poetry\.lock|uv\.lock|composer\.lock|Gemfile\.lock|packages\.lock\.json)$/,
  /\.min\.(js|css)$/,
  /\.snap$/,
  /(^|\/)(vendor|dist)\//,
];

export function isGeneratedPath(filePath: string): boolean {
  return generatedPaths.some((pattern) => pattern.test(filePath));
}
