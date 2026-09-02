/**
 * inspect-video — build a Layer-4 multi-modal inspection packet for a window.
 *
 *   npm run qa:inspect -- --manifest spec.qa-manifest.json --start 31.5 --end 33.0
 *   npm run qa:inspect -- --video out.mp4 --start 31.5 --end 33.0
 *   flags (default ON): --frames --audio --waveform --transcript
 *   optional: --out dir  --fps N (contact-sheet density)
 *
 * Prints the packet summary; files land in the packet dir.
 */
import { resolveFromInvoker } from "../src/env";

import { loadManifest } from "../src/manifest/schema";
import { inspectWindow } from "../src/inspect";
import type { EditManifest } from "../src/types";

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 ? process.argv[i + 1] : undefined;
}
const flag = (name: string) => process.argv.includes(`--${name}`);

async function main() {
  const start = Number(arg("start"));
  const end = Number(arg("end"));
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    console.error("usage: inspect-video (--manifest m.json | --video v.mp4) --start S --end E [--out dir]");
    process.exit(2);
    return;
  }

  let manifest: EditManifest;
  if (arg("manifest")) {
    manifest = loadManifest(resolveFromInvoker(arg("manifest")!));
    if (arg("video")) manifest.video = resolveFromInvoker(arg("video")!);
  } else if (arg("video")) {
    manifest = { version: 1, lane: "generic", video: resolveFromInvoker(arg("video")!), events: [] };
  } else {
    console.error("need --manifest or --video");
    process.exit(2);
    return;
  }

  const outDir = arg("out")
    ? resolveFromInvoker(arg("out")!)
    : resolveFromInvoker(
      manifest.video,
      "..",
      "_qa",
      "inspect",
      `${start.toFixed(1)}-${end.toFixed(1)}`
    );

  // Any explicit flag switches to opt-in mode; no flags = everything on.
  const anyFlag = ["frames", "audio", "waveform", "transcript"].some((f) => flag(f));
  const packet = await inspectWindow(
    manifest,
    start,
    end,
    outDir,
    anyFlag
      ? {
          frames: flag("frames"),
          audio: flag("audio"),
          waveform: flag("waveform"),
          transcript: flag("transcript"),
          fps: arg("fps") ? Number(arg("fps")) : undefined,
        }
      : { fps: arg("fps") ? Number(arg("fps")) : undefined },
    (m) => console.log(m)
  );

  console.log(packet.summary);
  console.log(`\nPacket: ${packet.dir}`);
}

main().catch((e) => {
  console.error(`[qa:inspect] fatal: ${(e as Error).message}`);
  process.exit(2);
});
