import { expect, test } from "bun:test";
import { managedPull } from "./entities";
import { resolveTrigger } from "./events";
import { eventContext, fixtureClone, fixtureIssue, fixturePull } from "../fixtures";
import type { GithubRequest } from "../types";

test("managed PR approval uses the latest label actor across event pages", async () => {
  for (const actor of [fixtureClone.botId, 999]) {
    const request: GithubRequest = async (_route, parameters) => ({
      data:
        Number(parameters?.page ?? 1) === 1
          ? Array.from({ length: 100 }, (_, index) => ({
              id: index,
              event: "labeled",
              label: { name: "shadowclone:managed" },
              actor: { id: fixtureClone.botId },
            }))
          : [
              {
                id: 101,
                event: "labeled",
                label: { name: "shadowclone:managed" },
                actor: { id: actor },
              },
            ],
    });
    const pull = {
      ...fixturePull,
      user: { id: 999 },
      labels: [{ name: "shadowclone:managed" }],
    };

    expect(await managedPull({ clone: fixtureClone, request, pull })).toBe(
      actor === fixtureClone.botId,
    );
  }
});

test("resume dispatch uses the latest pause label event after the first page", async () => {
  const request: GithubRequest = async (route, parameters) => ({
    data: route.endsWith("/events")
      ? Number(parameters?.page ?? 1) === 1
        ? Array.from({ length: 100 }, (_, index) => ({
            id: index,
            event: "unlabeled",
            label: { name: "shadowclone:paused" },
            actor: { login: fixtureClone.owner },
          }))
        : [
            {
              id: 200,
              event: "unlabeled",
              label: { name: "shadowclone:paused" },
              actor: { login: fixtureClone.owner },
            },
          ]
      : fixtureIssue,
  });
  const context = eventContext({
    payload: { action: "unlabeled", label: { name: "shadowclone:paused" } },
  });

  expect((await resolveTrigger({ clone: fixtureClone, context, request }))?.key).toBe(
    "issues:1:200",
  );
});

test("an incomplete event history cannot authorize managed work", async () => {
  const request: GithubRequest = async () => ({
    data: Array.from({ length: 100 }, (_, index) => ({
      id: index,
      event: "labeled",
      label: { name: "shadowclone:managed" },
      actor: { id: fixtureClone.botId },
    })),
  });
  const pull = {
    ...fixturePull,
    user: { id: 999 },
    labels: [{ name: "shadowclone:managed" }],
  };

  expect(await managedPull({ clone: fixtureClone, request, pull })).toBeFalse();
});
