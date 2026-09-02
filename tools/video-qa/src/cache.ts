/**
 * Layer-result cache. Key = sha256(video) + sha256(manifest) + rubric version +
 * model + layer — a rubric or model change correctly invalidates stale results.
 * Stored under `<pack>/tools/video-qa/.qa-cache/` (gitignored); override with
 * VIDEO_QA_CACHE_DIR.
 */
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import type { LayerResult } from "./types";
import { QA_PROMPT_VERSION } from "./types";
import { sha256Text } from "./ffmpeg";
import { ENGINE_ROOT } from "./env";

function cacheDir(): string {
  const dir = process.env.VIDEO_QA_CACHE_DIR || join(ENGINE_ROOT, ".qa-cache");
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function cacheKey(parts: {
  videoSha: string;
  manifestSha: string;
  layer: string;
  model?: string;
}): string {
  return sha256Text(
    [parts.videoSha, parts.manifestSha, QA_PROMPT_VERSION, parts.model ?? "-", parts.layer].join("|")
  ).slice(0, 24);
}

export function cacheGet(key: string): LayerResult | null {
  const p = join(cacheDir(), `${key}.json`);
  if (!existsSync(p)) return null;
  try {
    return JSON.parse(readFileSync(p, "utf8")) as LayerResult;
  } catch {
    return null;
  }
}

export async function cachePut(key: string, result: LayerResult): Promise<void> {
  await writeFile(join(cacheDir(), `${key}.json`), JSON.stringify(result));
}
