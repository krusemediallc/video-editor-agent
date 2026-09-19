"""Durable project receipts and explicit, resumable stage execution."""
import json
from pathlib import Path
import re
import subprocess
import uuid

from common import changed, fingerprint, locked, now, read_json, resolve, write_json

STAGES = ("ingest", "style", "edit", "sound", "qa", "review")
LANES = ("branded-ad-edit", "reel-recut", "arcads-video-edit", "recap-video", "hook-splitter", "hook-variations", "ai-audio-sound-design", "talking-head-image-overlays")
SKILLS = {"ingest": "video-edit-pipeline", "style": "reel-style-clone", "sound": "sound-design", "qa": "video-qa", "review": "video-review-canvas"}


def project_path(path):
    path = Path(path).resolve()
    return path if path.name == "project.json" else path / "project.json"


def load(path):
    data = read_json(path)
    if data.get("schemaVersion") != 1 or not isinstance(data.get("sources"), list):
        raise ValueError("Unsupported or malformed project.json")
    if list(data.get("stages", {})) != list(STAGES):
        raise ValueError("Project must contain the ordered ingest/style/edit/sound/qa/review stages")
    for key, stage in data["stages"].items():
        if stage.get("status") not in ("pending", "complete", "skipped", "running", "failed"):
            raise ValueError(f"Invalid stage status: {key}")
    return data


def create(path, name, lane, sources, style=None, sound=False):
    path = project_path(path)
    with locked(path):
        if path.exists():
            raise ValueError(f"Project already exists: {path}; use status/resume")
        items = [fingerprint(p, path.parent) for p in sources]
        if not items:
            raise ValueError("At least one --source is required")
        data = {"schemaVersion": 1, "id": str(uuid.uuid4()), "name": name or path.parent.name,
                "lane": lane, "createdAt": now(), "updatedAt": now(), "sources": items,
                "style": fingerprint(style, path.parent) if style else None,
                "stages": {}, "renders": [], "currentRender": None, "approvedCuts": [], "notes": [], "history": []}
        for key in STAGES:
            skip = (key == "style" and not style) or (key == "sound" and not sound)
            data["stages"][key] = {"status": "skipped" if skip else "pending", "artifacts": [],
                                   "skill": lane if key == "edit" else SKILLS[key]}
        write_json(path, data)
    return data


def assess(data, base):
    """Compute stale state without modifying receipts or silently accepting edits."""
    reasons = {key: [] for key in STAGES}
    for item in data["sources"]:
        issue = changed(item, base)
        if issue:
            reasons["ingest"].append(f"Source {issue}: {item['path']}")
    if data.get("style"):
        issue = changed(data["style"], base)
        if issue:
            reasons["style"].append(f"Style {issue}: {data['style']['path']}")
    for key, stage in data["stages"].items():
        if stage["status"] == "complete":
            for item in stage.get("artifacts", []):
                issue = changed(item, base)
                if issue:
                    reasons[key].append(f"Artifact {issue}: {item['path']}")
    render_issue = current_render_issue(data, base)
    if render_issue:
        reasons["qa"].append(render_issue)
    if any(n.get("status") != "resolved" for n in data["notes"]):
        reasons["review"].append("Reviewer notes remain open")
    result = []
    upstream = None
    for key in STAGES:
        stage = data["stages"][key]
        status = stage["status"]
        if status == "skipped" and not reasons[key]:
            result.append({"id": key, "status": status, "reasons": [], "skill": stage["skill"], "artifacts": stage.get("artifacts", [])})
            continue
        own = list(reasons[key])
        if upstream:
            own.append(f"Upstream stage needs attention: {upstream}")
        if own:
            status = "stale" if stage["status"] == "complete" or reasons[key] else "blocked"
        if status not in ("complete", "skipped") and upstream is None:
            upstream = key
        result.append({"id": key, "status": status, "reasons": own, "skill": stage["skill"],
                       "artifacts": stage.get("artifacts", []), "command": stage.get("command"),
                       "expectedArtifacts": stage.get("expectedArtifacts", [])})
    return result


def status(path):
    path = project_path(path)
    data = load(path)
    stages = assess(data, path.parent)
    next_stage = next((s for s in stages if s["status"] not in ("complete", "skipped")), None)
    return {"project": str(path), "id": data["id"], "name": data["name"], "lane": data["lane"],
            "sources": data["sources"], "style": data["style"], "stages": stages,
            "nextStage": next_stage, "currentRender": data["currentRender"],
            "renders": [{**r, "valid": changed(r, path.parent) is None} for r in data["renders"]],
            "approvedCuts": [{**a, "valid": changed(a, path.parent) is None} for a in data["approvedCuts"]],
            "openNotes": [n for n in data["notes"] if n.get("status") != "resolved"]}


def save(path, data, action, details):
    data["updatedAt"] = now()
    data["history"].append({"at": data["updatedAt"], "action": action, **details})
    write_json(path, data)


def invalidate_after(data, key):
    for later in STAGES[STAGES.index(key) + 1:]:
        stage = data["stages"][later]
        if stage["status"] != "skipped":
            stage["status"] = "pending"


def require_idle(data):
    running = next((key for key, stage in data["stages"].items() if stage["status"] == "running"), None)
    if running:
        raise ValueError(f"Stage {running} is already running; recover it only after verifying its process stopped")


def current_render_issue(data, base):
    if not data.get("currentRender"):
        return None
    item = next((r for r in data["renders"] if r["version"] == data["currentRender"]), None)
    if not item:
        return f"Current render is not registered: {data['currentRender']}"
    issue = changed(item, base)
    return f"Registered render {issue}: {item['path']}; restore it or register a new version" if issue else None


def invalidate_review(data):
    # Feedback may arrive while a command is running. Preserve its running receipt,
    # but make that attempt fail rather than certify a superseded review snapshot.
    data["reviewRevision"] = data.get("reviewRevision", 0) + 1
    if data["stages"]["review"]["status"] != "running":
        data["stages"]["review"]["status"] = "pending"


def require_completion_inputs(data, base, key):
    if key in ("qa", "review"):
        issue = current_render_issue(data, base)
        if issue:
            raise ValueError(issue)
    if key == "review" and any(n.get("status") != "resolved" for n in data["notes"]):
        raise ValueError("Resolve all reviewer notes before completing or skipping review")


def ready(data, base, key):
    for stage in assess(data, base)[:STAGES.index(key)]:
        if stage["status"] not in ("complete", "skipped"):
            raise ValueError(f"Finish or explicitly skip {stage['id']} before {key}: {'; '.join(stage['reasons'])}")


def checkpoint(path, key, artifacts, skip=None):
    path = project_path(path)
    with locked(path):
        data = load(path)
        require_idle(data)
        ready(data, path.parent, key)
        require_completion_inputs(data, path.parent, key)
        stage = data["stages"][key]
        if not skip and not artifacts:
            raise ValueError("A completed checkpoint needs at least one --artifact; use --skip REASON for an omitted stage")
        evidence = [fingerprint(p, path.parent) for p in artifacts]
        if key == "ingest" and not skip:
            data["sources"] = [fingerprint(resolve(p["path"], path.parent), path.parent) for p in data["sources"]]
        if key == "style" and data.get("style") and not skip:
            data["style"] = fingerprint(resolve(data["style"]["path"], path.parent), path.parent)
        elif key == "style" and evidence and not skip:
            data["style"] = dict(evidence[0])
        stage.update(status="skipped" if skip else "complete", artifacts=evidence, completedAt=now())
        stage["reason"] = skip
        invalidate_after(data, key)
        save(path, data, "checkpoint", {"stage": key, "status": stage["status"], "artifacts": evidence, "reason": skip})
    return stage


def configure(path, key, argv, artifacts):
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x or "\x00" in x for x in argv):
        raise ValueError("--command must be a JSON array of nonempty argument strings, not a shell command")
    path = project_path(path)
    with locked(path):
        data = load(path)
        require_idle(data)
        data["stages"][key].update(command=argv, expectedArtifacts=artifacts or [], status="pending")
        invalidate_after(data, key)
        save(path, data, "configure", {"stage": key})
    return data["stages"][key]


def run_next(path):
    path = project_path(path)
    with locked(path):
        data = load(path)
        require_idle(data)
        stages = assess(data, path.parent)
        stage_info = next((s for s in stages if s["status"] not in ("complete", "skipped")), None)
        if not stage_info:
            return {"message": "All stages complete"}
        key = stage_info["id"]
        stage = data["stages"][key]
        require_completion_inputs(data, path.parent, key)
        if not stage.get("command"):
            raise ValueError(f"Next stage {key} uses skill {stage['skill']}. Complete it and checkpoint, or configure an argv command before resume --run.")
        if not stage.get("expectedArtifacts"):
            raise ValueError("Configure --artifact output paths before running; exit code alone is not a checkpoint")
        # Capture pre-run inputs so changes during execution cannot be accepted silently.
        inputs = [fingerprint(resolve(s["path"], path.parent), path.parent) for s in data["sources"]]
        style = fingerprint(resolve(data["style"]["path"], path.parent), path.parent) if data.get("style") else None
        render_input = next((dict(r) for r in data["renders"] if r["version"] == data.get("currentRender")), None) if key in ("qa", "review") else None
        review_revision = data.get("reviewRevision", 0)
        attempt = uuid.uuid4().hex
        log_path = path.parent / "_runs" / f"{key}-{attempt}.log"
        log_path.parent.mkdir(exist_ok=True)
        stage.update(status="running", startedAt=now(), attempt=attempt)
        save(path, data, "start", {"stage": key, "attempt": attempt})
        argv = stage["command"]
    try:
        with log_path.open("w") as stream:
            proc = subprocess.run(argv, cwd=path.parent, stdout=stream, stderr=subprocess.STDOUT, check=False)
        if proc.returncode:
            raise ValueError(f"Stage {key} exited {proc.returncode}; see {log_path}")
        artifacts = [fingerprint(resolve(a, path.parent), path.parent) for a in stage["expectedArtifacts"]]
        with locked(path):
            data = load(path)
            stage = data["stages"][key]
            if stage["status"] != "running" or stage.get("attempt") != attempt:
                raise ValueError("Stage attempt was recovered or superseded; its result was not accepted")
            if any(changed(item, path.parent) for item in inputs) or (style and changed(style, path.parent)):
                raise ValueError("Source or style changed during the run; checkpoint refused")
            if render_input and (data.get("currentRender") != render_input["version"] or changed(render_input, path.parent)):
                raise ValueError("Registered render changed during the run; checkpoint refused")
            if key == "review" and data.get("reviewRevision", 0) != review_revision:
                raise ValueError("Review notes changed during the run; checkpoint refused")
            require_completion_inputs(data, path.parent, key)
            stage.update(status="complete", artifacts=artifacts, completedAt=now())
            stage.pop("error", None)
            if key == "ingest":
                data["sources"] = inputs
            if key == "style":
                data["style"] = style
            invalidate_after(data, key)
            save(path, data, "complete", {"stage": key, "attempt": attempt, "artifacts": artifacts})
    except (Exception, KeyboardInterrupt) as exc:
        with locked(path):
            data = load(path)
            stage = data["stages"][key]
            # Never let a late subprocess overwrite a recovery or a newer attempt.
            if stage["status"] == "running" and stage.get("attempt") == attempt:
                stage.update(status="failed", error=str(exc), finishedAt=now())
                save(path, data, "failed", {"stage": key, "attempt": attempt})
        raise
    return {"stage": key, "status": "complete", "log": str(log_path)}


def recover(path, key, reason):
    path = project_path(path)
    with locked(path):
        data = load(path)
        if data["stages"][key]["status"] != "running":
            raise ValueError("Only an interrupted running stage needs recovery")
        data["stages"][key].update(status="failed", error=reason)
        invalidate_after(data, key)
        save(path, data, "recover", {"stage": key, "reason": reason})
    return data["stages"][key]


def render(path, video, version):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", version):
        raise ValueError("Version must be a short filename-safe ID")
    path = project_path(path)
    with locked(path):
        data = load(path)
        require_idle(data)
        item = fingerprint(video, path.parent)
        existing = next((r for r in data["renders"] if r["version"] == version), None)
        if existing:
            if existing["sha256"] == item["sha256"] and existing["path"] == item["path"]:
                return existing
            raise ValueError("Version already registered; use a new version and a new file")
        if any(r["path"] == item["path"] for r in data["renders"]):
            raise ValueError("A new render version must use a new file")
        item.update(version=version, createdAt=now())
        data["renders"].append(item)
        data["currentRender"] = version
        # A new render needs fresh QA and review, even if its build was checkpointed earlier.
        for key in ("qa", "review"):
            data["stages"][key]["status"] = "pending"
        save(path, data, "render", {"version": version})
    return item


def approve(path, version, reason):
    path = project_path(path)
    with locked(path):
        data = load(path)
        item = next((r for r in data["renders"] if r["version"] == version), None)
        if not item:
            raise ValueError(f"Unknown render version: {version}")
        if changed(item, path.parent):
            raise ValueError("Render changed or disappeared since registration; cannot approve")
        receipt = {**item, "approvedAt": now(), "reason": reason}
        data["approvedCuts"] = [a for a in data["approvedCuts"] if a["version"] != version] + [receipt]
        save(path, data, "approve", {"version": version, "reason": reason})
    return receipt


def note(path, text, note_id=None, state="open", version=None, evidence=None):
    path = project_path(path)
    with locked(path):
        data = load(path)
        item = next((n for n in data["notes"] if n["id"] == note_id), None)
        if note_id and not item:
            raise ValueError(f"Unknown note: {note_id}")
        if not item:
            if not text:
                raise ValueError("A new note needs --text")
            item = {"id": uuid.uuid4().hex, "text": text, "status": "open", "version": version or data["currentRender"], "createdAt": now(), "evidence": []}
            data["notes"].append(item)
        if text:
            item["text"] = text
        if state == "resolved" and not (evidence or item["evidence"]):
            raise ValueError("Resolving a note requires --evidence (rendered frame/clip/report path or URL)")
        item["status"] = state
        item["updatedAt"] = now()
        if evidence:
            item["evidence"].extend(evidence)
        if state == "open":
            invalidate_review(data)
        save(path, data, "note", {"id": item["id"], "status": state})
    return item


def import_review(path, export_file):
    """Import the canvas's resolved view; raw event replay remains the canvas's job."""
    exported = read_json(export_file)
    items = exported.get("notes", exported.get("comments", []))
    if not isinstance(items, list):
        raise ValueError("Review export needs a notes or comments array")
    path = project_path(path)
    with locked(path):
        data = load(path)
        by_id = {n["id"]: n for n in data["notes"]}
        for record in items:
            item = record.get("data", record)
            identity = record.get("id", item.get("id"))
            if not identity or not item.get("text"):
                raise ValueError("Every imported note needs an ID and text")
            state = record.get("status", item.get("status", "open"))
            evidence = record.get("evidence", item.get("evidence", []))
            if state not in ("open", "resolved"):
                raise ValueError("Imported note status must be open/resolved")
            if state == "resolved" and not evidence:
                state = "open"
            by_id[identity] = {"id": identity, "text": item["text"], "status": state,
                               "version": item.get("version"), "time": item.get("t"),
                               "frame": item.get("frame"), "fps": item.get("fps"),
                               "evidence": evidence, "replies": record.get("replies", item.get("replies", [])),
                               "history": record.get("history", item.get("history", [])),
                               "createdAt": record.get("createdAt", item.get("createdAt")), "updatedAt": now()}
        data["notes"] = list(by_id.values())
        if items:
            invalidate_review(data)
        save(path, data, "import-review", {"count": len(items)})
    return {"imported": len(items), "open": sum(n["status"] == "open" for n in data["notes"])}
