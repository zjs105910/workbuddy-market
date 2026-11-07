import { fingerprint } from "../../shared/structured";
import { fixedGraderFingerprint } from "../identity";

export async function workflowGraderFingerprint() {
  const files = [];
  for (const file of ["report.ts", "cells.ts", "scores.ts"]) files.push([file, await Bun.file(`${import.meta.dir}/${file}`).text()]);
  return fingerprint({ native: await fixedGraderFingerprint(), files });
}
