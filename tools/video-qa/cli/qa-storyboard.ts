import { resolveFromInvoker } from "../src/env";
import { dirname, join } from "node:path";
import { parseArgs } from "node:util";
import { runStoryboardQa } from "../src/storyboard";

async function main() {
  const { values } = parseArgs({ options: {
    storyboard: { type: "string" }, html: { type: "string" }, video: { type: "string" }, out: { type: "string" }, json: { type: "boolean" },
  } });
  if (!values.storyboard || !values.html) throw new Error("usage: qa:storyboard --storyboard plan.json --html composition.html [--video render.mp4] [--out dir] [--json]");
  const storyboard = resolveFromInvoker(values.storyboard);
  const outDir = values.out ? resolveFromInvoker(values.out) : join(dirname(storyboard), "_qa", "storyboard");
  const report = await runStoryboardQa({ storyboard, html: resolveFromInvoker(values.html), video: values.video ? resolveFromInvoker(values.video) : undefined, outDir });
  if (values.json) console.log(JSON.stringify(report, null, 2));
  else console.log(`Static coverage: ${report.staticCoverage}; evidence: ${report.evidenceStatus}; rendered visibility: not verified\n${join(outDir, "storyboard-report.md")}`);
  process.exitCode = report.staticCoverage === "FAIL" || report.evidenceStatus === "incomplete" ? 2 : 0;
}
main().catch((e) => { console.error(`[qa:storyboard] ${(e as Error).message}`); process.exitCode = 2; });
