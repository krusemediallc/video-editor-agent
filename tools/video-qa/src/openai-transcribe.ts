/**
 * Minimal OpenAI `whisper-1` client for word timestamps — plain fetch, no SDK.
 * Used only as the fallback transcriber when whisper.cpp (via `npx hyperframes
 * transcribe`) is unavailable. Needs OPENAI_API_KEY in the environment / `.env`.
 */
export interface WhisperWord { word: string; start: number; end: number }
export interface WhisperSegment { start: number; end: number; text: string }
export interface WhisperVerboseResult {
  text: string;
  language: string;
  duration: number;
  segments: WhisperSegment[];
  words?: WhisperWord[];
}

export async function transcribeWithTimestamps(
  file: File,
  options?: { language?: string; prompt?: string; granularity?: Array<"word" | "segment"> }
): Promise<WhisperVerboseResult> {
  const key = process.env.OPENAI_API_KEY;
  if (!key) throw new Error("OPENAI_API_KEY not set");
  const form = new FormData();
  form.append("file", file, file.name || "audio.wav");
  form.append("model", "whisper-1");
  form.append("response_format", "verbose_json");
  for (const g of options?.granularity ?? ["segment"]) form.append("timestamp_granularities[]", g);
  if (options?.language) form.append("language", options.language);
  if (options?.prompt) form.append("prompt", options.prompt);

  const res = await fetch("https://api.openai.com/v1/audio/transcriptions", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}` },
    body: form,
  });
  if (!res.ok) {
    throw new Error(`openai transcription failed: ${res.status} ${(await res.text()).slice(0, 300)}`);
  }
  const data = (await res.json()) as {
    text: string;
    language?: string;
    duration?: number;
    segments?: Array<{ start: number; end: number; text: string }>;
    words?: Array<{ word: string; start: number; end: number }>;
  };
  return {
    text: data.text,
    language: data.language ?? "en",
    duration: data.duration ?? 0,
    segments: (data.segments ?? []).map((s) => ({ start: s.start, end: s.end, text: s.text.trim() })),
    words: data.words?.map((w) => ({ word: w.word.trim(), start: w.start, end: w.end })),
  };
}
