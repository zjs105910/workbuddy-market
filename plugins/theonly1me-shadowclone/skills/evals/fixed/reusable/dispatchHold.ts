import { retryEligible } from "./attempts";
import type { Cell } from "./schema";

export function unresolvedInfrastructure(cell: Cell) {
  if (retryEligible(cell)) return null;
  return (
    cell.attempts.at(-1)?.diagnostics.find((diagnostic) => diagnostic.stage !== "execution") ?? null
  );
}
