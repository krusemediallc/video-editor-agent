"""Offline behavior tests. Media cases generate their own tiny ffmpeg fixture."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True
import catalog
import project
from common import binary, command, read_json, write_json


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="editor-state-")
        self.root = Path(self.tmp.name)
        self.src = self.root / "source.mov"
        self.src.write_bytes(b"source identity")
        self.dir = self.root / "edit with spaces"
        self.file = self.dir / "project.json"
        project.create(self.dir, "Demo", "recap-video", [self.src])

    def tearDown(self):
        self.tmp.cleanup()

    def checkpoint(self, stage, content=b"artifact"):
        artifact = self.dir / (stage + ".txt")
        artifact.write_bytes(content)
        return project.checkpoint(self.dir, stage, [artifact])

    def test_fresh_session_resumes_next_stage_and_is_read_only(self):
        self.checkpoint("ingest")
        before = self.file.read_bytes()
        result = project.status(self.dir)
        self.assertEqual(result["nextStage"]["id"], "edit")
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(project.status(self.file)["id"], result["id"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            project.create(self.dir, "Replace", "recap-video", [self.src])

    def test_source_change_invalidates_finished_downstream_and_refreshes_at_ingest(self):
        for stage in ("ingest", "edit", "qa", "review"):
            self.checkpoint(stage)
        self.src.write_bytes(b"source changes")
        result = project.status(self.dir)
        self.assertEqual(result["nextStage"]["id"], "ingest")
        self.assertTrue(all(s["status"] == "stale" for s in result["stages"] if s["id"] not in ("sound", "style")))
        with self.assertRaisesRegex(ValueError, "ingest"):
            self.checkpoint("edit")
        self.checkpoint("ingest", b"fresh ingest")
        self.assertEqual(project.status(self.dir)["nextStage"]["id"], "edit")

    def test_missing_artifact_is_not_complete(self):
        self.checkpoint("ingest")
        self.checkpoint("edit")
        (self.dir / "edit.txt").unlink()
        state = project.status(self.dir)
        self.assertEqual(state["nextStage"]["status"], "stale")
        self.assertIn("missing", state["nextStage"]["reasons"][0])

    def test_style_chosen_after_intake_survives_resume(self):
        self.checkpoint("ingest")
        self.checkpoint("style", b"Chosen style guide")
        result = project.status(self.dir)
        self.assertEqual(result["style"]["path"], "style.txt")
        self.assertEqual(result["stages"][1]["artifacts"][0]["path"], "style.txt")
        (self.dir / "style.txt").write_bytes(b"Updated style guide")
        self.assertEqual(project.status(self.dir)["nextStage"]["id"], "style")

    def test_project_tree_can_move(self):
        self.checkpoint("ingest")
        moved = self.root.with_name(self.root.name + "-moved")
        shutil.copytree(self.root, moved)
        try:
            self.assertEqual(project.status(moved / self.dir.name)["nextStage"]["id"], "edit")
        finally:
            shutil.rmtree(moved)

    def test_render_versions_are_immutable_and_approval_has_hash(self):
        render = self.dir / "render-v1.mp4"
        render.write_bytes(b"render v1")
        project.render(self.dir, render, "v1")
        project.approve(self.dir, "v1", "Approved in review")
        self.assertTrue(project.status(self.dir)["approvedCuts"][0]["valid"])
        with self.assertRaisesRegex(ValueError, "new file"):
            project.render(self.dir, render, "v2")
        render.write_bytes(b"modified render")
        with self.assertRaisesRegex(ValueError, "Version already"):
            project.render(self.dir, render, "v1")
        self.assertFalse(project.status(self.dir)["approvedCuts"][0]["valid"])
        with self.assertRaisesRegex(ValueError, "changed"):
            project.approve(self.dir, "v1", "Cannot reuse approval")

    def test_notes_require_evidence_and_import_is_idempotent(self):
        note = project.note(self.dir, "Move caption")
        with self.assertRaisesRegex(ValueError, "requires --evidence"):
            project.note(self.dir, None, note["id"], "resolved")
        project.note(self.dir, None, note["id"], "resolved", evidence=["review/frame-v2.png"])
        self.assertEqual(project.status(self.dir)["openNotes"], [])
        export = self.dir / "review-export.json"
        write_json(export, {"notes": [{"id": "canvas-note", "text": "Fix seam", "status": "resolved", "evidence": [], "version": "v1", "t": 1.5}]})
        project.import_review(self.dir, export)
        project.import_review(self.dir, export)
        self.assertEqual(len(project.status(self.dir)["openNotes"]), 1)
        self.assertEqual(len(read_json(self.file)["notes"]), 2)

    def test_explicit_run_no_shell_and_only_one_stage(self):
        payload = "literal $HOME `do-not-run`"
        argv = [sys.executable, "-c", "from pathlib import Path; import sys; Path('receipt.txt').write_text(sys.argv[1])", payload]
        project.configure(self.dir, "ingest", argv, ["receipt.txt"])
        self.assertFalse((self.dir / "receipt.txt").exists())
        result = project.run_next(self.dir)
        self.assertEqual(result["status"], "complete")
        self.assertEqual((self.dir / "receipt.txt").read_text(), payload)
        self.assertEqual(project.status(self.dir)["nextStage"]["id"], "edit")
        self.assertTrue(Path(result["log"]).exists())

    def test_failed_command_and_missing_output_are_retryable(self):
        project.configure(self.dir, "ingest", [sys.executable, "-c", "raise SystemExit(7)"], ["missing.txt"])
        with self.assertRaisesRegex(ValueError, "exited 7"):
            project.run_next(self.dir)
        self.assertEqual(project.status(self.dir)["nextStage"]["status"], "failed")
        project.configure(self.dir, "ingest", [sys.executable, "-c", "pass"], ["missing.txt"])
        with self.assertRaisesRegex(ValueError, "does not exist"):
            project.run_next(self.dir)
        self.assertEqual(project.status(self.dir)["nextStage"]["status"], "failed")

    def test_stale_writer_and_running_stage_cannot_run_twice(self):
        from common import locked
        with locked(self.file):
            with self.assertRaisesRegex(ValueError, "Another writer"):
                project.checkpoint(self.dir, "ingest", [self.src])
        project.configure(self.dir, "ingest", [sys.executable, "-c", "pass"], ["missing.txt"])
        data = read_json(self.file)
        data["stages"]["ingest"]["status"] = "running"
        write_json(self.file, data)
        with self.assertRaisesRegex(ValueError, "already running"):
            project.run_next(self.dir)
        project.recover(self.dir, "ingest", "Verified interrupted process is stopped")
        self.assertEqual(project.status(self.dir)["nextStage"]["status"], "failed")

    def test_completion_requires_artifacts_and_dependencies(self):
        with self.assertRaisesRegex(ValueError, "artifact"):
            project.checkpoint(self.dir, "ingest", [])
        with self.assertRaisesRegex(ValueError, "ingest"):
            project.checkpoint(self.dir, "qa", [self.src])
        with self.assertRaisesRegex(ValueError, "JSON array"):
            project.configure(self.dir, "ingest", "echo shell", [])

    def test_changed_current_render_invalidates_qa_even_with_unchanged_reports(self):
        for stage in ("ingest", "edit"):
            self.checkpoint(stage)
        video = self.dir / "render-v1.mp4"
        video.write_bytes(b"render one")
        project.render(self.dir, video, "v1")
        for stage in ("qa", "review"):
            self.checkpoint(stage)
        self.assertIsNone(project.status(self.dir)["nextStage"])
        video.write_bytes(b"render overwritten")
        state = project.status(self.dir)
        self.assertEqual(state["nextStage"]["id"], "qa")
        self.assertEqual(state["nextStage"]["status"], "stale")
        self.assertFalse(state["renders"][0]["valid"])
        with self.assertRaisesRegex(ValueError, "Registered render changed"):
            project.checkpoint(self.dir, "qa", [self.dir / "qa.txt"])
        video.unlink()
        self.assertIn("missing", project.status(self.dir)["nextStage"]["reasons"][0])

    def test_running_stage_blocks_upstream_checkpoints_config_render_and_another_run(self):
        for stage in ("ingest", "edit"):
            self.checkpoint(stage)
        data = read_json(self.file)
        data["stages"]["qa"].update(status="running", attempt="active-attempt")
        write_json(self.file, data)
        self.src.write_bytes(b"upstream source changed while QA runs")
        before = self.file.read_bytes()
        actions = [lambda: project.checkpoint(self.dir, "ingest", [self.src]),
                   lambda: project.configure(self.dir, "ingest", [sys.executable, "-c", "pass"], ["receipt"]),
                   lambda: project.render(self.dir, self.src, "v1"),
                   lambda: project.run_next(self.dir)]
        for action in actions:
            with self.assertRaisesRegex(ValueError, "already running"):
                action()
            self.assertEqual(self.file.read_bytes(), before)

    def test_late_recovered_attempt_cannot_overwrite_new_attempt_success_or_failure(self):
        for old_returncode in (0, 7):
            with self.subTest(old_returncode=old_returncode):
                project.configure(self.dir, "ingest", [sys.executable, "-c", "pass"], ["receipt.txt"])
                calls = 0
                def simulated_process(*args, **kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        project.recover(self.dir, "ingest", "Confirmed old attempt stopped")
                        project.configure(self.dir, "ingest", [sys.executable, "-c", "pass"], ["receipt.txt"])
                        project.run_next(self.dir)
                        return subprocess.CompletedProcess(args[0], old_returncode)
                    (self.dir / "receipt.txt").write_text("new attempt output")
                    return subprocess.CompletedProcess(args[0], 0)
                with patch.object(project.subprocess, "run", side_effect=simulated_process):
                    with self.assertRaisesRegex(ValueError, "superseded|exited 7"):
                        project.run_next(self.dir)
                data = read_json(self.file)
                self.assertEqual(data["stages"]["ingest"]["status"], "complete")
                self.assertNotIn("error", data["stages"]["ingest"])
                self.assertEqual(data["history"][-1]["action"], "complete")
                self.assertEqual(data["history"][-1]["attempt"], data["stages"]["ingest"]["attempt"])

    def test_source_changed_during_run_is_not_accepted(self):
        project.configure(self.dir, "ingest", [sys.executable, "-c", "pass"], ["receipt.txt"])
        def simulated_process(*args, **kwargs):
            self.src.write_bytes(b"changed while running")
            (self.dir / "receipt.txt").write_text("output")
            return subprocess.CompletedProcess(args[0], 0)
        with patch.object(project.subprocess, "run", side_effect=simulated_process):
            with self.assertRaisesRegex(ValueError, "Source or style changed"):
                project.run_next(self.dir)
        self.assertEqual(read_json(self.file)["stages"]["ingest"]["status"], "failed")

    def test_current_render_changed_during_qa_is_not_accepted(self):
        for stage in ("ingest", "edit"):
            self.checkpoint(stage)
        video = self.dir / "render-v1.mp4"
        video.write_bytes(b"original render")
        project.render(self.dir, video, "v1")
        project.configure(self.dir, "qa", [sys.executable, "-c", "pass"], ["qa.txt"])
        def simulated_process(*args, **kwargs):
            video.write_bytes(b"replaced during QA")
            (self.dir / "qa.txt").write_text("passing report for wrong bytes")
            return subprocess.CompletedProcess(args[0], 0)
        with patch.object(project.subprocess, "run", side_effect=simulated_process):
            with self.assertRaisesRegex(ValueError, "Registered render changed during"):
                project.run_next(self.dir)
        self.assertEqual(read_json(self.file)["stages"]["qa"]["status"], "failed")

    def test_open_notes_and_import_require_fresh_review_and_preserve_frame_history(self):
        for stage in ("ingest", "edit", "qa", "review"):
            self.checkpoint(stage)
        note = project.note(self.dir, "Move caption")
        self.assertEqual(project.status(self.dir)["nextStage"]["id"], "review")
        with self.assertRaisesRegex(ValueError, "Resolve all reviewer notes"):
            project.checkpoint(self.dir, "review", [self.dir / "review.txt"])
        with self.assertRaisesRegex(ValueError, "Resolve all reviewer notes"):
            project.checkpoint(self.dir, "review", [], skip="Try to bypass feedback")
        project.note(self.dir, None, note["id"], "resolved", evidence=["frame-v2.png"])
        self.checkpoint("review")
        export = self.dir / "review-export.json"
        history = [{"id": "event-1", "data": {"commentId": "canvas-note", "kind": "status", "status": "resolved"}}]
        write_json(export, {"schemaVersion": 2, "notes": [{"id": "canvas-note", "text": "Exact frame", "status": "resolved",
                   "version": "v1", "t": 31 / 30, "frame": 31, "fps": 30, "history": history,
                   "evidence": [{"beforeFrame": 31, "afterFrame": 24}], "replies": [{"text": "Done"}]}]})
        project.import_review(self.dir, export)
        self.assertEqual(project.status(self.dir)["nextStage"]["id"], "review")
        imported = next(n for n in read_json(self.file)["notes"] if n["id"] == "canvas-note")
        self.assertEqual((imported["time"], imported["frame"], imported["fps"]), (31 / 30, 31, 30))
        self.assertEqual(imported["history"], history)
        self.assertEqual(imported["replies"][0]["text"], "Done")
        self.checkpoint("review")
        self.assertIsNone(project.status(self.dir)["nextStage"])
        # Read-only assessment still catches stale hand-edited completion receipts.
        data = read_json(self.file)
        data["notes"][0]["status"] = "open"
        write_json(self.file, data)
        self.assertEqual(project.status(self.dir)["nextStage"]["id"], "review")

    def test_feedback_during_review_run_refuses_old_completion_without_losing_note(self):
        for stage in ("ingest", "edit", "qa"):
            self.checkpoint(stage)
        project.configure(self.dir, "review", [sys.executable, "-c", "pass"], ["review.txt"])
        def simulated_process(*args, **kwargs):
            project.note(self.dir, "New feedback during review")
            self.assertEqual(read_json(self.file)["stages"]["review"]["status"], "running")
            (self.dir / "review.txt").write_text("old receipt")
            return subprocess.CompletedProcess(args[0], 0)
        with patch.object(project.subprocess, "run", side_effect=simulated_process):
            with self.assertRaisesRegex(ValueError, "Review notes changed"):
                project.run_next(self.dir)
        self.assertEqual(read_json(self.file)["stages"]["review"]["status"], "failed")
        self.assertEqual(len(project.status(self.dir)["openNotes"]), 1)

    def test_cli_status_and_errors(self):
        cli = Path(__file__).resolve().parents[1] / "editor.py"
        result = subprocess.run([sys.executable, cli, "project", "status", str(self.dir), "--json"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["name"], "Demo")
        result = subprocess.run([sys.executable, cli, "project", "init", str(self.dir), "--source", str(self.src)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.ffmpeg = binary("FFMPEG")
            binary("FFPROBE")
        except ValueError as exc:
            raise unittest.SkipTest(str(exc))
        cls.media = tempfile.TemporaryDirectory(prefix="catalog-media-")
        cls.source = Path(cls.media.name) / "shot.mov"
        command([cls.ffmpeg, "-nostdin", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=96x96:rate=30:duration=2",
                 "-f", "lavfi", "-i", "sine=frequency=440:duration=2:sample_rate=48000", "-c:v", "libx264", "-preset", "ultrafast",
                 "-c:a", "pcm_s16le", "-shortest", cls.source])

    @classmethod
    def tearDownClass(cls):
        cls.media.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="catalog-test-")
        self.root = Path(self.tmp.name)
        self.src = self.root / "talking head.mov"
        shutil.copyfile(self.source, self.src)
        self.path = self.root / "library.json"
        self.transcript = self.root / "talking head.words.json"
        write_json(self.transcript, {"words": [{"word": "Product", "start": 0.1, "end": .4}, {"word": "launch.", "start": .4, "end": .7}]})

    def tearDown(self):
        self.tmp.cleanup()

    def test_ingest_generates_real_derivatives_and_indexes_sidecar(self):
        result = catalog.ingest(self.path, [self.src], tags=["creator"])
        self.assertFalse(result["assets"][0]["cached"])
        asset = catalog.search(self.path, "product launch")[0]
        self.assertEqual(asset["matchingPhrases"][0]["start"], .1)
        self.assertEqual(asset["video"]["width"], 96)
        self.assertEqual(asset["audio"]["sample_rate"], "48000")
        for key in ("poster", "contactSheet"):
            self.assertGreater((self.root / asset[key]).stat().st_size, 100)
        self.assertEqual(catalog.search(self.path, "nonexistent"), [])

    def test_duplicate_move_cache_and_transcript_update(self):
        first = catalog.ingest(self.path, [self.src])["assets"][0]["id"]
        moved = self.root / "renamed.mov"
        shutil.copyfile(self.src, moved)
        with patch.object(catalog, "make_thumbnails", side_effect=AssertionError("Unchanged media re-rendered")), patch.object(catalog, "probe", side_effect=AssertionError("Unchanged media re-probed")):
            second = catalog.ingest(self.path, [moved])["assets"][0]
        self.assertTrue(second["cached"])
        self.assertEqual(first, second["id"])
        self.assertEqual(len(read_json(self.path)["assets"]), 1)
        write_json(self.transcript, [{"text": "Corrected", "start": .1, "end": .4}])
        catalog.ingest(self.path, [self.src])
        self.assertEqual(len(catalog.search(self.path, "corrected")), 1)
        self.assertEqual(catalog.search(self.path, "launch"), [])

    def test_restrictions_intervals_use_and_offline_search(self):
        identity = catalog.ingest(self.path, [self.src])["assets"][0]["id"]
        catalog.annotate(self.path, identity, label="Stage demonstration", tags=["event"], interval=(.1, .8, "Clean intro"), restriction="Slide permission pending")
        asset = catalog.search(self.path, "clean intro", tag="event", unused=True)[0]
        self.assertEqual(asset["restrictions"], ["Slide permission pending"])
        catalog.record_use(self.path, identity, self.root / "project", "v1", .1, .8)
        catalog.record_use(self.path, identity, self.root / "project", "v1", .1, .8)
        self.assertEqual(catalog.search(self.path, "", unused=True), [])
        self.assertEqual(len(catalog.search(self.path, "")[0]["uses"]), 1)
        self.src.unlink()
        self.assertIsNone(catalog.search(self.path, "")[0]["availablePath"])

    def test_bad_timestamps_never_persist(self):
        identity = catalog.ingest(self.path, [self.src])["assets"][0]["id"]
        before = self.path.read_bytes()
        for interval in ((1, .2, "reversed"), (0, 3, "outside"), (float("nan"), 1, "not finite")):
            with self.assertRaises(ValueError):
                catalog.annotate(self.path, identity, interval=interval)
            self.assertEqual(self.path.read_bytes(), before)
        write_json(self.transcript, [{"text": "outside", "start": 9, "end": 10}])
        with self.assertRaisesRegex(ValueError, "exceed"):
            catalog.ingest(self.path, [self.src])
        self.assertEqual(self.path.read_bytes(), before)

    def test_replaced_media_is_never_returned_as_old_asset(self):
        old = catalog.ingest(self.path, [self.src])["assets"][0]["id"]
        catalog.annotate(self.path, old, tags=["original"])
        self.src.write_bytes(self.src.read_bytes() + b"changed container bytes")
        old_result = next(a for a in catalog.search(self.path, "") if a["id"] == old)
        self.assertIsNone(old_result["availablePath"])
        new = catalog.ingest(self.path, [self.src])["assets"][0]["id"]
        self.assertNotEqual(old, new)
        results = {a["id"]: a for a in catalog.search(self.path, "")}
        self.assertEqual(results[old]["paths"], [])
        self.assertIsNone(results[old]["availablePath"])
        self.assertEqual(results[old]["tags"], ["original"])
        self.assertEqual(Path(results[new]["availablePath"]), self.src.resolve())

    def test_malformed_transcript_cannot_replace_valid_index(self):
        catalog.ingest(self.path, [self.src])
        before = self.path.read_bytes()
        malformed = [{"unrecognized": []}, [{"text": "No timing"}],
                     [{"text": "Missing end", "start": .1}],
                     [{"text": "Missing offset", "offsets": {"from": 100}}],
                     [{"text": "Bad offset", "offsets": {"from": None, "to": 400}}],
                     ["not a row"], [{"text": 42, "start": .1, "end": .4}]]
        for transcript in malformed:
            with self.subTest(transcript=transcript):
                write_json(self.transcript, transcript)
                with self.assertRaises(ValueError):
                    catalog.ingest(self.path, [self.src])
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(len(catalog.search(self.path, "product launch")), 1)
        write_json(self.transcript, {"transcription": [{"text": "Whisper offsets", "offsets": {"from": 100, "to": 700}}]})
        catalog.ingest(self.path, [self.src])
        phrase = catalog.search(self.path, "whisper offsets")[0]["matchingPhrases"][0]
        self.assertEqual((phrase["start"], phrase["end"]), (.1, .7))

    def test_missing_derivative_regenerates_without_losing_annotations(self):
        identity = catalog.ingest(self.path, [self.src])["assets"][0]["id"]
        catalog.annotate(self.path, identity, tags=["selected"])
        sheet = self.root / read_json(self.path)["assets"][0]["contactSheet"]
        sheet.unlink()
        catalog.ingest(self.path, [self.src])
        self.assertTrue(sheet.is_file())
        self.assertEqual(len(catalog.search(self.path, "", tag="selected")), 1)


if __name__ == "__main__":
    unittest.main()
