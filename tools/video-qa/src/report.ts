/**
 * Report aggregation: merge layer results, apply corroboration, compute the
 * verdict, and emit qa-report.json + qa-report.md.
 *
 * Issues are anchored to manifest event ids — comparing anchored issues across
 * re-renders is how resolution tracking survives timeline shifts.
 */
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { LayerResult, QaIssue, QaReport, Severity, Verdict } from "./types";
import { QA_PROMPT_VERSION } from "./types";

const SEV_ORDER: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];

function overlaps(a: QaIssue, b: QaIssue, slack = 1.0): boolean {
  if (a.eventId && b.eventId && a.eventId === b.eventId) return true;
  return (
    a.timeWindow.start - slack < b.timeWindow.end &&
    b.timeWindow.start - slack < a.timeWindow.end
  );
}

export function aggregate(args: {
  video: string;
  videoSha256: string;
  manifestPath?: string;
  manifestSha256?: string;
  model?: string;
  iteration: number;
  technical: LayerResult;
  transcript: LayerResult;
  semantic: LayerResult;
}): QaReport {
  const { technical, transcript, semantic } = args;
  const deterministic = [...technical.issues, ...transcript.issues];

  // Corroboration: a semantic finding matching a deterministic finding raises
  // confidence on both. Gemini-only issues stay ≤ HIGH.
  for (const sIssue of semantic.issues) {
    for (const dIssue of deterministic) {
      if (overlaps(sIssue, dIssue)) {
        sIssue.corroborated = true;
        dIssue.corroborated = true;
      }
    }
  }

  const issues = [...deterministic, ...semantic.issues].sort(
    (a, b) =>
      SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity) ||
      a.timeWindow.start - b.timeWindow.start
  );

  const summary: Record<Severity, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
  for (const i of issues) summary[i.severity] += 1;

  let verdict: Verdict = "PASS";
  if (summary.CRITICAL > 0 || summary.HIGH > 0) verdict = "FAIL";
  else if (summary.MEDIUM > 0) verdict = "PASS_WITH_WARNINGS";
  // LOW-only never blocks (spec: do not auto-reject on LOW).

  return {
    video: args.video,
    videoSha256: args.videoSha256,
    manifestPath: args.manifestPath,
    manifestSha256: args.manifestSha256,
    promptVersion: QA_PROMPT_VERSION,
    model: args.model,
    generatedAt: new Date().toISOString(),
    iteration: args.iteration,
    verdict,
    layers: { technical, transcript, semantic },
    issues,
    summary,
  };
}

export function renderMarkdown(report: QaReport): string {
  const l = report.layers;
  const layerLine = (name: string, r: LayerResult) =>
    `- **${name}**: ${r.status}${r.reason ? ` (${r.reason})` : ""} — ${r.issues.length} issue(s)`;
  const lines = [
    `# Video QA report — ${report.verdict}`,
    ``,
    `Video: \`${report.video}\``,
    `Generated: ${report.generatedAt} · iteration ${report.iteration} · rubric v${report.promptVersion}${report.model ? ` · ${report.model}` : ""}`,
    ``,
    layerLine("Technical (ffmpeg)", l.technical),
    layerLine("Transcript boundary", l.transcript),
    layerLine("Semantic (Gemini)", l.semantic),
    ``,
    `Severity: ${report.summary.CRITICAL} critical · ${report.summary.HIGH} high · ${report.summary.MEDIUM} medium · ${report.summary.LOW} low`,
    ``,
  ];
  if (!report.issues.length) {
    lines.push(`No issues found. Clean pass.`);
  } else {
    lines.push(`## Issues`, ``);
    for (const i of report.issues) {
      lines.push(
        `### ${i.severity} · ${i.category} · ${i.id}`,
        `- window: ${i.timeWindow.start.toFixed(2)}–${i.timeWindow.end.toFixed(2)}s${i.eventId ? ` · anchor: \`${i.eventId}\`` : ""}${i.corroborated ? " · **corroborated by 2 layers**" : ""}${i.objective ? "" : " · subjective"}`,
        `- ${i.message}`,
        ...(i.suggestedFix
          ? [`- suggested fix: \`${i.suggestedFix.action}\` ${JSON.stringify(i.suggestedFix.params ?? {})}`]
          : []),
        ``
      );
    }
  }
  return lines.join("\n");
}

export async function writeReport(report: QaReport, outDir: string): Promise<void> {
  await writeFile(join(outDir, "qa-report.json"), JSON.stringify(report, null, 1));
  await writeFile(join(outDir, "qa-report.md"), renderMarkdown(report));
}

/** Exit code contract for skills: 0 pass, 1 warnings, 2 fail. */
export function exitCode(verdict: Verdict): number {
  return verdict === "PASS" ? 0 : verdict === "PASS_WITH_WARNINGS" ? 1 : 2;
}
