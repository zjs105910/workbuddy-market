import path from "node:path";
import { readFileSync } from "node:fs";

export function runtimeSources(): Record<string, string> {
  const transpiler = new Bun.Transpiler({ loader: "ts" });
  const files = [
    "guard/records",
    "guard/comment",
    "guard/entities",
    "guard/reviewRequest",
    "guard/events",
    "guard/policy",
    "react",
  ];
  const entries = files.map((name) => {
    const source = transpiler.transformSync(
      readFileSync(path.join(import.meta.dir, `${name}.ts`), "utf8"),
    );
    const names = [...source.matchAll(/^export (?:async )?function (\w+)/gm)].flatMap((match) =>
      match[1] ? [match[1]] : [],
    );
    const common = source
      .replace(
        /^import\s+([\s\S]*?)\s+from\s+["']([^"']+)["'];?$/gm,
        (_match: string, bindings: string, location: string) => {
          const imported = location.startsWith(".") ? `${location}.cjs` : location;

          return `const ${bindings} = require(${JSON.stringify(imported)});`;
        },
      )
      .replace(/^export (?=(?:async )?function)/gm, "");

    return [
      `.github/shadowclone/${name}.cjs`,
      `${common}\nmodule.exports = { ${names.join(", ")} };\n`,
    ] as const;
  });

  return Object.fromEntries(entries);
}
