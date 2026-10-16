import { expect, test } from "bun:test";
import { createGitFixture } from "../collect/gitFixture";
import { preparePacket } from "./index";

function lockfile(versions: { readonly lodash: string; readonly leftPad: string }): string {
  return JSON.stringify(
    { lockfileVersion: 3, packages: { "": {}, "node_modules/lodash": { version: versions.lodash }, "node_modules/left-pad": { version: versions.leftPad } } },
    null,
    2,
  );
}

test("a dependency that the base branch upgraded after the pull request branched is not counted as added", async () => {
  const fixture = await createGitFixture();
  const checkout = (branch: string) => Bun.spawnSync(["git", "checkout", "--quiet", branch], { cwd: fixture.directory });
  await fixture.write({ "package-lock.json": lockfile({ lodash: "4.17.20", leftPad: "1.3.0" }) });
  fixture.commit("fork point");
  Bun.spawnSync(["git", "checkout", "--quiet", "-b", "feature"], { cwd: fixture.directory });
  await fixture.write({ "package-lock.json": lockfile({ lodash: "4.17.20", leftPad: "1.3.1" }) });
  const headSha = fixture.commit("upgrade left-pad");
  checkout("main");
  await fixture.write({ "package-lock.json": lockfile({ lodash: "4.17.21", leftPad: "1.3.0" }) });
  const baseSha = fixture.commit("upgrade lodash on main");
  checkout("feature");

  const packet = await preparePacket({
    facts: { repository: "example/app", number: 1, title: "t", body: "", baseRefName: "main", baseSha, headSha },
    checkout: fixture.directory,
    network: false,
  });

  expect(packet.reports.map((report) => report.detail)).toEqual(["the network is off, so 1 changed packages were not checked"]);
});
