"""Setup safety tests: no network, real user config or machine changes."""
from contextlib import redirect_stdout
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("editor_setup", Path(__file__).resolve().parents[1] / "setup.py")
setup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="editor setup tests ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "pack with spaces"
        self.root.mkdir()
        (self.root / ".env.example").write_text("ELEVENLABS_API_KEY=\n")
        (self.root / "MASTER_CONTEXT.template.md").write_text("# Context template\n")
        self.working = Path(self.temp.name) / "working repo"
        self.working.mkdir()
        for name in ("new", "existing-file", "existing-dir", "existing-link"):
            source = self.root / ".claude/skills" / name
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text("Skill\n")

    def quietly(self, fn, *args, **kwargs):
        with redirect_stdout(io.StringIO()):
            return fn(*args, **kwargs)

    def test_config_copy_is_idempotent_and_preserves_personal_content(self):
        target = self.root / ".env"
        self.quietly(setup.copy_if_absent, self.root / ".env.example", target)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        target.write_text("PERSONAL_SETTING=keep\n")
        self.quietly(setup.copy_if_absent, self.root / ".env.example", target)
        self.assertEqual(target.read_text(), "PERSONAL_SETTING=keep\n")

    def test_links_are_relative_idempotent_and_do_not_clobber(self):
        target = self.working / ".claude/skills"
        target.mkdir(parents=True)
        (target / "existing-file").write_text("keep file")
        (target / "existing-dir").mkdir()
        (target / "existing-link").symlink_to("missing-private-skill")
        for _ in range(2):
            self.quietly(setup.link_skills, self.root, self.working)
        self.assertFalse(os.path.isabs(os.readlink(target / "new")))
        self.assertEqual((target / "new").resolve(), (self.root / ".claude/skills/new").resolve())
        self.assertEqual((target / "existing-file").read_text(), "keep file")
        self.assertTrue((target / "existing-dir").is_dir())
        self.assertEqual(os.readlink(target / "existing-link"), "missing-private-skill")

    def test_dry_run_changes_nothing_in_either_workspace(self):
        before = sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))
        with mock.patch.object(setup, "ROOT", self.root), mock.patch.object(setup, "run") as run:
            code = self.quietly(setup.main, ["--dry-run", "--no-install", "--link-skills", str(self.working)])
        self.assertEqual(code, 0)
        self.assertEqual(before, sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*")))
        self.assertEqual(list(self.working.iterdir()), [])
        run.assert_not_called()

    def test_no_install_never_runs_installer_or_edits_git_config(self):
        with mock.patch.object(setup, "ROOT", self.root), mock.patch.object(setup, "doctor", return_value=0), \
             mock.patch.object(setup, "run") as run, mock.patch.object(setup, "install_dependencies") as install:
            for _ in range(2):
                self.assertEqual(self.quietly(setup.main, ["--no-install"]), 0)
        run.assert_not_called()
        install.assert_not_called()
        self.assertTrue((self.root / "MASTER_CONTEXT.md").is_file())
        self.assertFalse((self.root / ".git").exists())

    def test_local_doctor_has_no_node_or_api_requirement(self):
        (self.root / "MASTER_CONTEXT.md").write_text("local context")
        with mock.patch.object(setup, "binary", return_value="/fixture/tool"), \
             mock.patch.object(setup, "node_ready", side_effect=AssertionError("not needed")), \
             mock.patch.object(setup, "has_key", side_effect=AssertionError("not needed")), \
             mock.patch.object(setup, "run") as run:
            self.assertEqual(self.quietly(setup.doctor, self.root, "local"), 0)
        run.assert_not_called()

    def test_sound_lane_requires_key_without_revealing_it(self):
        (self.root / "MASTER_CONTEXT.md").write_text("local context")
        with mock.patch.object(setup, "binary", return_value="/fixture/tool"), \
             mock.patch.object(setup, "node_ready", return_value=True), \
             mock.patch.object(setup.shutil, "which", return_value="/fixture/tool"), \
             mock.patch.dict(os.environ, {"ELEVENLABS_API_KEY": ""}):
            self.assertEqual(self.quietly(setup.doctor, self.root, "sound-design"), 1)
            (self.root / ".env").write_text("ELEVENLABS_API_KEY=example-test-value\n")
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(setup.doctor(self.root, "sound-design"), 0)
            self.assertNotIn("example-test-value", output.getvalue())

    def test_check_mode_never_creates_context(self):
        with mock.patch.object(setup, "ROOT", self.root), mock.patch.object(setup, "binary", return_value="/fixture/tool"):
            self.assertEqual(self.quietly(setup.main, ["--check", "--lane", "local"]), 1)
        self.assertFalse((self.root / "MASTER_CONTEXT.md").exists())
        self.assertFalse((self.root / ".env").exists())


if __name__ == "__main__":
    unittest.main()
