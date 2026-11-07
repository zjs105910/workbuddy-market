import path from "node:path";
import { runFakeGh } from "./index";

const root = path.dirname(path.dirname(process.execPath));
const outcome = runFakeGh({ root, cwd: process.cwd(), args: process.argv.slice(2) });

process.stdout.write(outcome.stdout);
process.stderr.write(outcome.stderr);
process.exit(outcome.exitCode);
