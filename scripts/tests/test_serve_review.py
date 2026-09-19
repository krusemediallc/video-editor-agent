"""Real HTTP checks for the byte-range server used by browser video playback."""
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest

SPEC = importlib.util.spec_from_file_location("serve_review", Path(__file__).resolve().parents[1] / "serve-review.py")
server_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server_module)


class QuietHandler(server_module.ReviewHandler):
    def log_message(self, *_args):
        pass


class RangeServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="review http tests ")
        cls.root = Path(cls.temp.name) / "review"
        cls.root.mkdir()
        cls.payload = bytes(range(256)) * 1024
        (cls.root / "clip.mp4").write_bytes(cls.payload)
        (cls.root / "empty.mp4").write_bytes(b"")
        (cls.root / "index.html").write_text("<h1>Review</h1>")
        (cls.root / "app.mjs").write_text("export const ready = true;")
        (Path(cls.temp.name) / "outside.txt").write_text("private")
        (cls.root / "outside.txt").symlink_to(Path(cls.temp.name) / "outside.txt")
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(cls.root)))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temp.cleanup()

    def request(self, method="GET", path="/clip.mp4", headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_head_and_full_get_advertise_ranges_and_exact_length(self):
        status, headers, body = self.request("HEAD")
        self.assertEqual((status, body), (200, b""))
        self.assertEqual(headers["Content-Length"], str(len(self.payload)))
        self.assertEqual(headers["Accept-Ranges"], "bytes")
        self.assertEqual(headers["Content-Type"], "video/mp4")
        status, headers, body = self.request()
        self.assertEqual((status, body), (200, self.payload))

    def test_bounded_open_ended_and_suffix_ranges(self):
        for value, start, end in (("bytes=7-47", 7, 47), ("bytes=262100-", 262100, 262143),
                                  ("bytes=-19", 262125, 262143), ("bytes=262140-999999", 262140, 262143)):
            with self.subTest(value=value):
                status, headers, body = self.request(headers={"Range": value})
                self.assertEqual(status, 206)
                self.assertEqual(body, self.payload[start:end + 1])
                self.assertEqual(headers["Content-Range"], f"bytes {start}-{end}/{len(self.payload)}")
                self.assertEqual(int(headers["Content-Length"]), end - start + 1)

    def test_invalid_unsatisfiable_and_empty_ranges(self):
        for value in ("bytes=999999-", "bytes=5-2", "bytes=-0", "bytes=-", "bytes=1-2,4-5", "items=0-1"):
            with self.subTest(value=value):
                status, headers, body = self.request(headers={"Range": value})
                self.assertEqual((status, body), (416, b""))
                self.assertEqual(headers["Content-Range"], f"bytes */{len(self.payload)}")
        self.assertEqual(self.request(path="/empty.mp4", headers={"Range": "bytes=0-0"})[0], 416)

    def test_if_range_falls_back_to_full_file_when_identity_changed(self):
        _, head, _ = self.request("HEAD")
        self.assertEqual(self.request(headers={"Range": "bytes=0-7", "If-Range": head["ETag"]})[0], 206)
        status, _, body = self.request(headers={"Range": "bytes=0-7", "If-Range": '"old-file"'})
        self.assertEqual((status, body), (200, self.payload))

    def test_review_entry_modules_and_directory_boundary(self):
        self.assertEqual(self.request(path="/")[2], b"<h1>Review</h1>")
        self.assertIn("javascript", self.request(path="/app.mjs")[1]["Content-Type"])
        self.assertEqual(self.request(path="/outside.txt")[0], 404)
        self.assertEqual(self.request(path="/missing.mp4")[0], 404)


if __name__ == "__main__":
    unittest.main()
