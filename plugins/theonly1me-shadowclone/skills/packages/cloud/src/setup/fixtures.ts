import { generateKeyPairSync } from "node:crypto";
import type { App } from "./app";
import type { Repository } from "../types";
import type { GhApiCall, GhResponse } from "./ghApi";

export function syntheticApp(): App {
  const { privateKey } = generateKeyPairSync("rsa", { modulusLength: 2048 });

  return {
    id: 20,
    slug: "sample-clone",
    owner: { login: "sample" },
    pem: privateKey.export({ type: "pkcs1", format: "pem" }).toString(),
  };
}

export const setupRepository: Repository = {
  id: 10,
  full_name: "sample/project",
  default_branch: "main",
  owner: { login: "sample", type: "User" },
  permissions: { admin: true },
};

export function ghApiFixture(routes: Readonly<Record<string, GhResponse | ((body: unknown) => GhResponse)>>) {
  const calls: { readonly method: string; readonly route: string; readonly body: unknown }[] = [];
  const call: GhApiCall = async (options) => {
    const method = options.method ?? "GET";
    const key = `${method} ${options.route}`;
    const response = routes[key];

    calls.push({ method, route: options.route, body: options.body });

    if (response === undefined) {
      return { status: 404, data: { message: `No synthetic route for ${key}` } };
    }

    return typeof response === "function" ? response(options.body) : response;
  };

  return { call, calls };
}
