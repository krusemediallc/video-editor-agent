"""Small, dependency-free persistence helpers shared by the editor tools."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def write_json(path, data):
    """Readers see either the old document or the complete new document."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def locked(path):
    """Serialize writers without a third-party database or dependency."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name("." + path.name + ".lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValueError(f"Another writer owns {lock}. If interrupted, verify its PID is no longer running before removing the lock.") from exc
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        lock.unlink(missing_ok=True)


def relative(path, base):
    return os.path.relpath(Path(path).resolve(), Path(base).resolve())


def resolve(path, base):
    return (Path(base) / path).resolve()


def fingerprint(path, base):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError(f"File does not exist: {path}")
    return {"path": relative(path, base), "sha256": digest(path), "bytes": path.stat().st_size}


def changed(item, base):
    path = resolve(item["path"], base)
    if not path.is_file():
        return "missing"
    return "changed" if digest(path) != item["sha256"] else None


def binary(name):
    value = os.environ.get(name) or os.environ.get(name + "_PATH")
    executable = name.lower().replace("_", "-")
    value = value or shutil.which(executable)
    if not value:
        for prefix in ("/opt/homebrew/bin", "/usr/local/bin"):
            candidate = Path(prefix) / executable
            if candidate.is_file():
                value = str(candidate)
                break
    if not value:
        raise ValueError(f"{name.lower()} is required; install it or set {name}.")
    return value


def command(argv, timeout=300):
    result = subprocess.run([str(x) for x in argv], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f"{Path(str(argv[0])).name} failed ({result.returncode}): {result.stderr[-3000:]}")
    return result.stdout


def finite(value, label, minimum=0):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{label} must be a finite number >= {minimum}")
    return value
