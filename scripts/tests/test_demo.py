"""Opt-in real-media integration test; never downloads models or calls APIs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get("EDITOR_INTEGRATION_TESTS") == "1", "use bash scripts/test.sh --integration for real-media demo")
class DemoTests(unittest.TestCase):
    def test_full_demo_and_overwrite_refusal(self):
        with tempfile.TemporaryDirectory(prefix="editor demo with spaces ") as folder:
            output = Path(folder) / "demo output"
            command = [sys.executable, str(ROOT / "scripts/demo.py"), "--output", str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stdout[-12000:] + result.stderr[-12000:])
            receipt = json.loads((output / "demo-result.json").read_text())
            self.assertEqual(receipt["frames"], 120)
            self.assertEqual(receipt["paidCalls"], 0)
            for key in ("video", "review", "project", "catalog", "storyboard", "pixelProof"):
                self.assertTrue((output / receipt[key]).is_file(), key)
            status = json.loads((output / "project-status.json").read_text())
            self.assertIsNone(status["nextStage"])
            self.assertTrue(json.loads((output / "catalog-search.json").read_text()))
            self.assertTrue(all(sample["passed"] for sample in json.loads((output / receipt["pixelProof"]).read_text())["samples"]))
            before = (output / receipt["video"]).read_bytes()
            repeated = subprocess.run(command, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("Nothing overwritten", repeated.stderr)
            self.assertEqual(before, (output / receipt["video"]).read_bytes())


if __name__ == "__main__":
    unittest.main()
