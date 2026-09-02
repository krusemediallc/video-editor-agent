/**
 * Minimal Gemini REST client (fetch-based, like src/services/anthropic.ts — no
 * SDK dependency). Supports the Files API (resumable upload + ACTIVE polling)
 * and generateContent with enforced JSON responseSchema.
 *
 * Key: GEMINI_API_KEY (X-goog-api-key header). Model: GEMINI_QA_MODEL, default
 * "gemini-flash-latest" (alias tracks the current Flash model, avoids id churn).
 */
import { readFile, stat } from "node:fs/promises";

const BASE = "https://generativelanguage.googleapis.com";

export function geminiKey(): string | null {
  return process.env.GEMINI_API_KEY || null;
}

export function geminiModel(): string {
  return process.env.GEMINI_QA_MODEL || "gemini-flash-latest";
}

export interface GeminiFile {
  name: string;
  uri: string;
  state: string;
  mimeType: string;
}

/** Resumable upload to the Gemini Files API; polls until ACTIVE (videos need
 *  server-side processing before they're usable). */
export async function uploadFileToGemini(
  path: string,
  mimeType: string,
  displayName: string,
  log: (msg: string) => void = () => {}
): Promise<GeminiFile> {
  const key = geminiKey();
  if (!key) throw new Error("GEMINI_API_KEY not set");
  const size = (await stat(path)).size;

  const start = await fetch(`${BASE}/upload/v1beta/files`, {
    method: "POST",
    headers: {
      "X-goog-api-key": key,
      "X-Goog-Upload-Protocol": "resumable",
      "X-Goog-Upload-Command": "start",
      "X-Goog-Upload-Header-Content-Length": String(size),
      "X-Goog-Upload-Header-Content-Type": mimeType,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ file: { display_name: displayName } }),
  });
  if (!start.ok) throw new Error(`Gemini upload start failed: ${start.status} ${await start.text()}`);
  const uploadUrl = start.headers.get("x-goog-upload-url");
  if (!uploadUrl) throw new Error("Gemini upload start returned no upload URL");

  const bytes = await readFile(path);
  const up = await fetch(uploadUrl, {
    method: "POST",
    headers: {
      "X-Goog-Upload-Command": "upload, finalize",
      "X-Goog-Upload-Offset": "0",
      "Content-Length": String(size),
    },
    body: new Uint8Array(bytes),
  });
  if (!up.ok) throw new Error(`Gemini upload failed: ${up.status} ${await up.text()}`);
  const uploaded = (await up.json()) as { file: GeminiFile };
  let file = uploaded.file;

  const deadline = Date.now() + 5 * 60 * 1000;
  while (file.state === "PROCESSING" && Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 4000));
    const poll = await fetch(`${BASE}/v1beta/${file.name}`, {
      headers: { "X-goog-api-key": key },
    });
    if (!poll.ok) throw new Error(`Gemini file poll failed: ${poll.status}`);
    file = (await poll.json()) as GeminiFile;
    log(`[qa:L3] gemini file ${file.state.toLowerCase()}…`);
  }
  if (file.state !== "ACTIVE") {
    throw new Error(`Gemini file never became ACTIVE (state=${file.state})`);
  }
  return file;
}

export interface GeminiPart {
  text?: string;
  file_data?: { file_uri: string; mime_type: string };
  video_metadata?: { fps?: number };
}

/** generateContent with an enforced JSON response schema. Returns parsed JSON. */
export async function geminiGenerateJson<T>(
  parts: GeminiPart[],
  responseSchema: Record<string, unknown>,
  opts?: { model?: string; temperature?: number }
): Promise<T> {
  const key = geminiKey();
  if (!key) throw new Error("GEMINI_API_KEY not set");
  const model = opts?.model ?? geminiModel();
  let res: Response | null = null;
  for (let attempt = 0; attempt < 3; attempt++) {
    res = await fetch(`${BASE}/v1beta/models/${model}:generateContent`, {
      method: "POST",
      headers: { "X-goog-api-key": key, "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts }],
        generationConfig: {
          temperature: opts?.temperature ?? 0.2,
          responseMimeType: "application/json",
          responseSchema,
        },
      }),
    });
    // 503 = transient overload; back off and retry before giving up.
    if (res.status !== 503 && res.status !== 429) break;
    await new Promise((r) => setTimeout(r, 15_000 * (attempt + 1)));
  }
  if (!res || !res.ok) {
    throw new Error(`Gemini generateContent failed: ${res?.status} ${await res?.text()}`);
  }
  const data = (await res.json()) as {
    candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }>;
  };
  const text = data.candidates?.[0]?.content?.parts?.map((p) => p.text ?? "").join("") ?? "";
  if (!text) throw new Error("Gemini returned an empty response");
  return JSON.parse(text) as T;
}
