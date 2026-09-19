"""Content-addressed media catalog, thumbnails and transcript search. No cloud calls."""
from pathlib import Path
import re
import tempfile

from common import binary, command, digest, finite, locked, now, read_json, relative, resolve, write_json

MEDIA = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi", ".wav", ".mp3", ".m4a", ".aac", ".flac"}


def load(path):
    if not Path(path).exists():
        return {"schemaVersion": 1, "assets": [], "updatedAt": now()}
    data = read_json(path)
    if data.get("schemaVersion") != 1 or not isinstance(data.get("assets"), list):
        raise ValueError("Unsupported or malformed catalog")
    return data


def probe(path):
    import json
    return json.loads(command([binary("FFPROBE"), "-v", "error", "-show_format", "-show_streams", "-of", "json", path]))


def transcript_segments(path):
    data = read_json(path)
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        field = next((key for key in ("words", "segments", "transcription") if key in data), None)
        if field is None:
            raise ValueError("Transcript must contain words/segments/transcription")
        rows = data[field]
    else:
        raise ValueError("Transcript must be an array or contain words/segments/transcription")
    if not isinstance(rows, list):
        raise ValueError("Transcript rows must be an array")
    segments = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each transcript row must be an object")
        text = row.get("text", row.get("word", ""))
        if not isinstance(text, str):
            raise ValueError("Transcript text must be a string")
        text = text.strip()
        if not text or text.startswith("[_"):
            continue
        if "start" in row or "end" in row:
            if "start" not in row or "end" not in row:
                raise ValueError("Transcript timestamps need both start and end")
            start, end = row["start"], row["end"]
        else:
            offsets = row.get("offsets")
            if not isinstance(offsets, dict) or "from" not in offsets or "to" not in offsets:
                raise ValueError("Transcript timestamps need start/end or offsets.from/to")
            start = finite(offsets["from"], "transcript offset from") / 1000
            end = finite(offsets["to"], "transcript offset to") / 1000
        finite(start, "transcript start")
        finite(end, "transcript end")
        if end < start:
            raise ValueError("Transcript end cannot precede start")
        segments.append({"start": start, "end": end, "text": text})
    return sorted(segments, key=lambda s: s["start"])


def phrases(segments):
    """Group word timestamps into searchable intervals; never rank creative quality."""
    grouped = []
    current = None
    for segment in segments:
        if current and (segment["start"] - current["end"] > 0.8 or segment["end"] - current["start"] > 8):
            grouped.append(current)
            current = None
        if current:
            current["text"] += " " + segment["text"]
            current["end"] = max(current["end"], segment["end"])
        else:
            current = dict(segment)
        if re.search(r"[.!?]$", segment["text"]):
            grouped.append(current)
            current = None
    if current:
        grouped.append(current)
    return grouped


def local_transcribe(source, work, model, whisper_bin=None):
    if not model or not Path(model).is_file():
        raise ValueError("--transcribe needs an existing --whisper-model (no model is downloaded)")
    exe = whisper_bin or binary("WHISPER_CLI")
    with tempfile.TemporaryDirectory(prefix="catalog-whisper-") as temporary:
        wav = Path(temporary) / "audio.wav"
        command([binary("FFMPEG"), "-nostdin", "-v", "error", "-i", source, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", wav])
        prefix = Path(temporary) / "transcript"
        command([exe, "-m", Path(model).resolve(), "-f", wav, "-oj", "-of", prefix], timeout=3600)
        output = work / "transcript.json"
        write_json(output, read_json(prefix.with_suffix(".json")))
    return output


def make_thumbnails(source, work, duration):
    work.mkdir(parents=True, exist_ok=True)
    poster = work / "poster.jpg"
    sheet = work / "contact-sheet.jpg"
    command([binary("FFMPEG"), "-nostdin", "-v", "error", "-y", "-ss", str(min(duration / 2, 2)),
             "-i", source, "-frames:v", "1", "-vf", "scale=320:-2", "-q:v", "3", poster])
    # Twelve evenly spaced frames, letterboxed to a constant cell size.
    filt = f"fps=12/{max(duration, 0.01)},scale=240:136:force_original_aspect_ratio=decrease:force_divisible_by=2,pad=240:136:(ow-iw)/2:(oh-ih)/2,tile=4x3"
    command([binary("FFMPEG"), "-nostdin", "-v", "error", "-y", "-i", source, "-vf", filt,
             "-frames:v", "1", "-q:v", "3", sheet])
    if not poster.is_file() or not sheet.is_file():
        raise ValueError("ffmpeg produced no thumbnails; check the input video")
    return poster, sheet


def inputs(paths, recursive=False):
    found = []
    for value in paths:
        p = Path(value).resolve()
        if p.is_dir():
            found.extend(sorted(x for x in (p.rglob("*") if recursive else p.iterdir()) if x.is_file() and x.suffix.lower() in MEDIA))
        elif p.is_file() and p.suffix.lower() in MEDIA:
            found.append(p)
        else:
            raise ValueError(f"Not a supported media file or directory: {p}")
    return list(dict.fromkeys(found))


def ingest(path, paths, recursive=False, transcript=None, tags=None, transcribe=False, model=None, whisper_bin=None):
    path = Path(path).resolve()
    files = inputs(paths, recursive)
    if not files:
        raise ValueError("No media files found")
    if transcript and len(files) != 1:
        raise ValueError("--transcript applies to exactly one media file; use sidecar transcripts for a batch")
    result = []
    with locked(path):
        data = load(path)
        by_hash = {a["sha256"]: a for a in data["assets"]}
        for source in files:
            sha = digest(source)
            asset = by_hash.get(sha)
            cached = asset is not None
            media_path = relative(source, path.parent)
            work = path.parent / (path.stem + ".assets") / sha[:20]
            if not asset:
                metadata = probe(source)
                video = next((s for s in metadata.get("streams", []) if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")), None)
                audio = next((s for s in metadata.get("streams", []) if s["codec_type"] == "audio"), None)
                duration = float(metadata.get("format", {}).get("duration", (video or audio or {}).get("duration", 0)))
                finite(duration, "media duration")
                if duration <= 0 or not (video or audio):
                    raise ValueError(f"Cannot catalog media without a positive duration: {source}")
                asset = {"id": "asset-" + sha[:20], "sha256": sha, "paths": [], "label": source.stem,
                         "duration": duration, "bytes": source.stat().st_size, "kind": "video" if video else "audio",
                         "video": {k: video.get(k) for k in ("width", "height", "avg_frame_rate", "codec_name")} if video else None,
                         "audio": {k: audio.get(k) for k in ("channels", "sample_rate", "codec_name")} if audio else None,
                         "tags": [], "intervals": [], "restrictions": [], "uses": [], "transcript": None,
                         "createdAt": now()}
                data["assets"].append(asset)
                by_hash[sha] = asset
            # A path identifies a current location, never an asset's content identity.
            # Detach a replaced file from the old hash while retaining its annotations.
            for previous in data["assets"]:
                if previous["sha256"] != sha and media_path in previous["paths"]:
                    previous["paths"].remove(media_path)
            if media_path not in asset["paths"]:
                asset["paths"].append(media_path)
            asset["tags"] = sorted(set(asset["tags"] + (tags or [])))
            if asset["kind"] == "video" and (not asset.get("poster") or not resolve(asset["poster"], path.parent).is_file() or not asset.get("contactSheet") or not resolve(asset["contactSheet"], path.parent).is_file()):
                poster, sheet = make_thumbnails(source, work, asset["duration"])
                asset.update(poster=relative(poster, path.parent), contactSheet=relative(sheet, path.parent))
            sidecar = Path(transcript).resolve() if transcript else next((p for p in (source.with_suffix(".words.json"), source.with_suffix(".transcript.json")) if p.is_file()), None)
            if not sidecar and transcribe:
                if not asset["audio"]:
                    raise ValueError(f"Cannot transcribe a video without audio: {source}")
                work.mkdir(parents=True, exist_ok=True)
                prior = asset.get("transcript") or {}
                model_hash = digest(model) if model and Path(model).is_file() else None
                prior_file = resolve(prior.get("path", "nonexistent"), path.parent)
                if model_hash and prior.get("modelSha256") == model_hash and prior_file.is_file() and digest(prior_file) == prior.get("sha256"):
                    sidecar = prior_file
                else:
                    sidecar = local_transcribe(source, work, model, whisper_bin)
                    asset["transcript"] = {"modelSha256": model_hash}
            if sidecar:
                sha_transcript = digest(sidecar)
                if (asset.get("transcript") or {}).get("sha256") != sha_transcript:
                    segments = transcript_segments(sidecar)
                    if any(s["start"] > asset["duration"] + 0.5 or s["end"] > asset["duration"] + 0.5 for s in segments):
                        raise ValueError("Transcript times exceed source duration; supply source-time words")
                    asset["transcript"] = {**(asset.get("transcript") or {}), "path": relative(sidecar, path.parent),
                                           "sha256": sha_transcript, "segments": segments, "phrases": phrases(segments)}
            asset["updatedAt"] = now()
            result.append({"id": asset["id"], "path": media_path, "cached": cached, "transcript": bool(asset["transcript"])})
        data["updatedAt"] = now()
        write_json(path, data)
    return {"catalog": str(path), "assets": result}


def get_asset(data, identity):
    asset = next((a for a in data["assets"] if a["id"] == identity), None)
    if not asset:
        raise ValueError(f"Unknown asset: {identity}")
    return asset


def annotate(path, identity, label=None, tags=None, interval=None, restriction=None):
    path = Path(path).resolve()
    with locked(path):
        data = load(path)
        asset = get_asset(data, identity)
        if label is not None:
            asset["label"] = label
        asset["tags"] = sorted(set(asset["tags"] + (tags or [])))
        if restriction and restriction not in asset["restrictions"]:
            asset["restrictions"].append(restriction)
        if interval:
            start, end, text = float(interval[0]), float(interval[1]), interval[2]
            finite(start, "interval start")
            finite(end, "interval end")
            if end <= start or end > asset["duration"]:
                raise ValueError("Interval must be nonempty and within the source duration")
            item = {"start": start, "end": end, "label": text}
            if item not in asset["intervals"]:
                asset["intervals"].append(item)
        asset["updatedAt"] = now()
        data["updatedAt"] = now()
        write_json(path, data)
    return asset


def record_use(path, identity, project, version=None, start=None, end=None):
    path = Path(path).resolve()
    with locked(path):
        data = load(path)
        asset = get_asset(data, identity)
        if (start is None) != (end is None):
            raise ValueError("Provide both --start and --end, or neither")
        if start is not None:
            finite(start, "use start")
            finite(end, "use end")
            if end <= start or end > asset["duration"]:
                raise ValueError("Use interval must be nonempty and within source duration")
        entry = {"project": relative(project, path.parent), "version": version, "start": start, "end": end}
        if not any(all(u.get(k) == v for k, v in entry.items()) for u in asset["uses"]):
            asset["uses"].append({**entry, "recordedAt": now()})
        asset["updatedAt"] = now()
        data["updatedAt"] = now()
        write_json(path, data)
    return asset["uses"]


def search(path, query, tag=None, unused=False):
    path = Path(path).resolve()
    terms = query.casefold().split()
    matches = []
    checked_paths = {}

    def available_path(asset):
        for location in asset["paths"]:
            candidate = resolve(location, path.parent)
            if candidate not in checked_paths:
                try:
                    checked_paths[candidate] = digest(candidate) if candidate.is_file() else None
                except OSError:
                    checked_paths[candidate] = None
            if checked_paths[candidate] == asset["sha256"]:
                return str(candidate)
        return None

    for asset in load(path)["assets"]:
        if tag and tag not in asset["tags"]:
            continue
        if unused and asset["uses"]:
            continue
        transcript = asset.get("transcript") or {}
        sections = transcript.get("phrases", [])
        searchable = " ".join([asset["label"], *asset["paths"], *asset["tags"], *asset["restrictions"],
                                *(i["label"] for i in asset["intervals"]), *(s["text"] for s in sections)]).casefold()
        if all(t in searchable for t in terms):
            available = available_path(asset)
            matching = [s for s in sections if all(t in s["text"].casefold() for t in terms)]
            matches.append({**asset, "availablePath": available, "matchingPhrases": matching})
    return matches
