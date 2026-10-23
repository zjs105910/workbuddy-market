import type { Stack, StackContext } from "../types";

function firstExisting(options: {
  readonly context: StackContext;
  readonly candidates: readonly string[];
}): string | null {
  return options.candidates.find((candidate) => options.context.exists(candidate)) ?? null;
}

function dotnetProject(context: StackContext): string | null {
  const glob = new Bun.Glob("*.{slnx,sln,csproj}");
  const [first] = [...glob.scanSync({ cwd: context.root, onlyFiles: true })].sort();

  return first ?? null;
}

export const goStack: Stack = {
  id: "go",
  sources: /\.go$|(?:^|\/)go\.(?:mod|sum)$/,
  detect: (context) => context.exists("go.mod"),
  install: () => ["go", "mod", "download"],
  commands: [
    { tool: "go vet", scope: "new-in-head", parser: "colon", command: () => ["go", "vet", "./..."] },
    {
      tool: "gofmt",
      scope: "changed-files",
      parser: "file-list",
      command: (context) => {
        const files = context.changedFiles.filter((file) => file.endsWith(".go") && context.exists(file));

        return files.length > 0 ? ["gofmt", "-l", ...files] : null;
      },
    },
  ],
};

export const rustStack: Stack = {
  id: "rust",
  sources: /\.rs$|(?:^|\/)Cargo\.(?:toml|lock)$/,
  detect: (context) => context.exists("Cargo.toml"),
  install: () => null,
  commands: [
    {
      tool: "clippy",
      scope: "new-in-head",
      parser: "colon",
      command: () => ["cargo", "clippy", "--all-targets", "--message-format", "short", "--quiet"],
    },
  ],
};

export const mavenStack: Stack = {
  id: "java-maven",
  sources: /\.(?:java|kt)$|(?:^|\/)pom\.xml$/,
  detect: (context) => context.exists("pom.xml"),
  install: () => null,
  commands: [
    {
      tool: "maven compile",
      scope: "new-in-head",
      parser: "maven",
      command: (context) => [context.exists("mvnw") ? "./mvnw" : "mvn", "-q", "-B", "-DskipTests", "compile"],
    },
  ],
};

export const gradleStack: Stack = {
  id: "java-gradle",
  sources: /\.(?:java|kt|kts|gradle)$/,
  detect: (context) =>
    firstExisting({
      context,
      candidates: ["build.gradle", "build.gradle.kts", "settings.gradle", "settings.gradle.kts"],
    }) !== null,
  install: () => null,
  commands: [
    {
      tool: "gradle classes",
      scope: "new-in-head",
      parser: "gradle",
      command: (context) => [context.exists("gradlew") ? "./gradlew" : "gradle", "--quiet", "--console=plain", "classes"],
    },
  ],
};

export const dotnetStack: Stack = {
  id: "dotnet",
  sources: /\.(?:cs|csproj|sln|slnx|props|targets)$/,
  detect: (context) => dotnetProject(context) !== null,
  install: () => null,
  commands: [
    {
      tool: "dotnet build",
      scope: "new-in-head",
      parser: "paren",
      command: (context) => {
        const project = dotnetProject(context);

        return project === null ? null : ["dotnet", "build", project, "-nologo", "-clp:NoSummary", "-v", "q"];
      },
    },
  ],
};
