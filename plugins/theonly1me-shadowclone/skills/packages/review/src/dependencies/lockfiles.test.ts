import { expect, test } from "bun:test";
import { lockfileParser } from "./lockfiles";

function parse(options: { readonly path: string; readonly text: string }): readonly string[] {
  return (lockfileParser(options.path)?.(options.text) ?? []).map((entry) => `${entry.ecosystem} ${entry.name} ${entry.version}`);
}

test("npm lockfiles name each installed package and version", () => {
  const packageLock = JSON.stringify({
    lockfileVersion: 3,
    packages: { "": { name: "app" }, "node_modules/lodash": { version: "4.17.20" }, "node_modules/a/node_modules/@scope/b": { version: "1.0.0" } },
  });
  const bunLock = '{\n  "lockfileVersion": 1,\n  "packages": {\n    "lodash": ["lodash@4.17.20", "", {}, "sha512-x"],\n  },\n}\n';
  const yarnClassic = '"lodash@^4.17.0":\n  version "4.17.20"\n  resolved "https://registry.example/lodash"\n';
  const yarnBerry = '"@scope/b@npm:^1.0.0":\n  version: 1.0.0\n  resolution: "@scope/b@npm:1.0.0"\n';
  const pnpm = "packages:\n\n  lodash@4.17.20:\n    resolution: {integrity: sha512-x}\n\n  '@scope/b@1.0.0':\n    resolution: {integrity: sha512-y}\n";

  expect(parse({ path: "package-lock.json", text: packageLock })).toEqual(["npm lodash 4.17.20", "npm @scope/b 1.0.0"]);
  expect(parse({ path: "bun.lock", text: bunLock })).toEqual(["npm lodash 4.17.20"]);
  expect(parse({ path: "yarn.lock", text: yarnClassic })).toEqual(["npm lodash 4.17.20"]);
  expect(parse({ path: "web/yarn.lock", text: yarnBerry })).toEqual(["npm @scope/b 1.0.0"]);
  expect(parse({ path: "pnpm-lock.yaml", text: pnpm })).toEqual(["npm lodash 4.17.20", "npm @scope/b 1.0.0"]);
});

test("Python, Rust, Go, Ruby, PHP, and .NET lockfiles name each registry package", () => {
  const uvLock = '[[package]]\nname = "requests"\nversion = "2.31.0"\nsource = { registry = "https://pypi.org/simple" }\n\n[[package]]\nname = "app"\nversion = "0.1.0"\nsource = { editable = "." }\n';
  const cargoLock = '[[package]]\nname = "serde"\nversion = "1.0.190"\nsource = "registry+https://github.com/rust-lang/crates.io-index"\n\n[[package]]\nname = "app"\nversion = "0.1.0"\n';
  const goModule = "module example.com/app\n\nrequire (\n\tgithub.com/gin-gonic/gin v1.9.0\n\tgolang.org/x/net v0.17.0 // indirect\n)\n";
  const gemfileLock = "GEM\n  remote: https://rubygems.org/\n  specs:\n    rack (2.2.8)\n    nokogiri (1.15.4-x86_64-linux)\n";
  const composerLock = JSON.stringify({ packages: [{ name: "guzzlehttp/guzzle", version: "v7.8.0" }] });
  const nugetLock = JSON.stringify({ dependencies: { "net8.0": { "Newtonsoft.Json": { type: "Direct", resolved: "13.0.1" }, App: { type: "Project" } } } });

  expect(parse({ path: "uv.lock", text: uvLock })).toEqual(["PyPI requests 2.31.0"]);
  expect(parse({ path: "requirements-dev.txt", text: "flask==2.3.2\nrequests[socks]==2.31.0 ; python_version > '3.8'\n-e .\n" })).toEqual(["PyPI flask 2.3.2", "PyPI requests 2.31.0"]);
  expect(parse({ path: "Cargo.lock", text: cargoLock })).toEqual(["crates.io serde 1.0.190"]);
  expect(parse({ path: "go.mod", text: goModule })).toEqual(["Go github.com/gin-gonic/gin v1.9.0", "Go golang.org/x/net v0.17.0"]);
  expect(parse({ path: "Gemfile.lock", text: gemfileLock })).toEqual(["RubyGems rack 2.2.8", "RubyGems nokogiri 1.15.4"]);
  expect(parse({ path: "composer.lock", text: composerLock })).toEqual(["Packagist guzzlehttp/guzzle 7.8.0"]);
  expect(parse({ path: "packages.lock.json", text: nugetLock })).toEqual(["NuGet Newtonsoft.Json 13.0.1"]);
});

test("a file that is not a lockfile has no parser", () => {
  expect(lockfileParser("src/package.json")).toBeNull();
});
