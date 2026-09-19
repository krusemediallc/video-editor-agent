#!/usr/bin/env python3
"""Serve a review directory on localhost with byte ranges for video seeking.

Usage: python3 scripts/serve-review.py --directory outputs/demo/review --port 8765
No upload or shared note backend: local review notes remain in the browser.
"""
import argparse
from email.utils import parsedate_to_datetime
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import re
import shutil


class ReviewHandler(SimpleHTTPRequestHandler):
    """Static files with one RFC 9110 bytes range; never list directories."""
    protocol_version = "HTTP/1.1"
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".mjs": "text/javascript", ".mp4": "video/mp4"}

    def send_head(self):
        self.byte_range = None
        root = Path(self.directory).resolve()
        requested = Path(self.translate_path(self.path))
        try:
            path = requested.resolve(strict=True)
            if not path.is_relative_to(root):
                self.send_error(HTTPStatus.NOT_FOUND)
                return None
            if path.is_dir():
                path = (path / "index.html").resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return None
            source = path.open("rb")
        except (OSError, ValueError, RuntimeError):
            self.send_error(HTTPStatus.NOT_FOUND)
            return None

        try:
            stat = os.fstat(source.fileno())
            size = stat.st_size
            etag = '"{:x}-{:x}"'.format(stat.st_mtime_ns, size)
            requested_range = self.headers.get("Range") if self.command == "GET" else None
            if_range = self.headers.get("If-Range")
            if requested_range and if_range and not self.range_matches(if_range, etag, stat.st_mtime):
                requested_range = None
            if requested_range:
                selected = self.parse_range(requested_range, size)
                if selected is None:
                    source.close()
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", "bytes */{}".format(size))
                    self.send_header("Content-Length", "0")
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    return None
                self.byte_range = selected
            self.send_response(HTTPStatus.PARTIAL_CONTENT if self.byte_range else HTTPStatus.OK)
            self.send_header("Content-Type", self.guess_type(str(path)))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("ETag", etag)
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.send_header("Cache-Control", "no-cache")
            if self.byte_range:
                start, end = self.byte_range
                self.send_header("Content-Range", "bytes {}-{}/{}".format(start, end, size))
                self.send_header("Content-Length", str(end - start + 1))
                source.seek(start)
            else:
                self.send_header("Content-Length", str(size))
            self.end_headers()
            return source
        except BaseException:
            source.close()
            raise

    @staticmethod
    def range_matches(value, etag, modified):
        if value.startswith('"') or value.startswith("W/"):
            return value == etag
        try:
            return int(parsedate_to_datetime(value).timestamp()) >= int(modified)
        except (TypeError, ValueError, OverflowError):
            return False

    @staticmethod
    def parse_range(value, size):
        # Multipart ranges are unnecessary for HTML video and intentionally rejected.
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
        if not match or size == 0:
            return None
        first, last = match.groups()
        if not first:
            count = int(last) if last else 0
            return (max(0, size - count), size - 1) if count > 0 else None
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
        if start >= size or end < start:
            return None
        return start, end

    def copyfile(self, source, outputfile):
        try:
            if self.byte_range is None:
                shutil.copyfileobj(source, outputfile)
                return
            remaining = self.byte_range[1] - self.byte_range[0] + 1
            while remaining:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                outputfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            # Browsers cancel an old range request when the reviewer seeks again.
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path, help="review directory containing index.html")
    parser.add_argument("--port", default=8765, type=int, help="localhost TCP port; 0 chooses a free port")
    args = parser.parse_args()
    directory = args.directory.expanduser().resolve()
    if not directory.is_dir() or not (directory / "index.html").is_file():
        parser.error("--directory must contain the generated review index.html")
    if not 0 <= args.port <= 65535:
        parser.error("--port must be between 0 and 65535")
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(ReviewHandler, directory=str(directory)))
    except OSError as error:
        parser.error(str(error))
    print("Review server: http://127.0.0.1:{}/".format(server.server_port), flush=True)
    print("Serving {}. Ctrl-C stops the server.".format(directory), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
