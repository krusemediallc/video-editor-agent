/**
 * Environment bootstrap for the video-qa engine.
 *
 * Loads `.env` files without overriding variables already in the environment:
 *   1. the directory the command was invoked from (npm exposes it as INIT_CWD when
 *      the engine is run via `npm --prefix <this dir> run …` from a working repo),
 *      walking up to the filesystem root;
 *   2. the skill pack's own repo root (`<pack>/.env`).
 * First definition wins, so a working repo's `.env` takes precedence over the pack's.
 *
 * Also exports the invoker's cwd so CLI path arguments resolve relative to where the
 * user typed the command, not to this package directory.
 */
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";

const HERE = dirname(fileURLToPath(import.meta.url));
/** `<pack>/tools/video-qa` */
export const ENGINE_ROOT = resolve(HERE, "..");
/** the skill-pack repo root (`<pack>`) */
export const PACK_ROOT = resolve(HERE, "..", "..", "..");
/** where the user invoked the command from */
export const INVOKE_CWD = process.env.INIT_CWD || process.cwd();

const loaded = new Set<string>();
function loadEnvFile(p: string): void {
  if (loaded.has(p) || !existsSync(p)) return;
  loaded.add(p);
  dotenv.config({ path: p });
}

let dir = INVOKE_CWD;
for (;;) {
  loadEnvFile(join(dir, ".env"));
  const parent = dirname(dir);
  if (parent === dir) break;
  dir = parent;
}
loadEnvFile(join(PACK_ROOT, ".env"));

/** Resolve a user-supplied path against the invoker's cwd (absolute paths pass through). */
export function resolveFromInvoker(...parts: string[]): string {
  return resolve(INVOKE_CWD, ...parts);
}
