import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from helpers import FakeDecisions

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from highways import evalset


class EvalWrittenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        self.env = {"HIGHWAYS_STATE": str(self.root / "state"),
                    "HIGHWAYS_CONFIG": str(self.root / "config.json"),
                    "OPENROUTER_API_KEY": "test-key"}

    def tearDown(self):
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.source), *args], check=True, text=True,
                              capture_output=True).stdout.strip()

    def write(self, name, text="x\n"):
        path = self.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, subject):
        self.git("add", ".")
        self.git("commit", "-qm", subject)
        return self.git("rev-parse", "HEAD")

    def routed_revision(self):
        self.write("AGENTS.md", "General guidance.\n")
        self.write("lib/AGENTS.md", "Read `thing.py`.\n")
        self.write("lib/thing.py", "answer = 1\n")
        return self.commit("initial")

    def input(self, rows):
        path = self.root / "written-input.jsonl"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def test_written_maps_at_pinned_revision_and_batches_without_overwrite(self):
        rev = self.routed_revision()
        (self.source / "moved").mkdir()
        self.git("mv", "lib/thing.py", "moved/thing.py")
        self.commit("move implementation")
        rows = self.input([{"question": "where does the implementation live", "files": ["lib/thing.py"]},
                           {"question": "what should we do next now", "files": []}])
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(evalset.written(str(self.source), rev, str(rows)), 0)
            self.assertEqual(evalset.written(str(self.source), rev, str(rows)), 0)
        first = self.root / "state" / "eval" / "source-written-1-questions.jsonl"
        second = self.root / "state" / "eval" / "source-written-2-questions.jsonl"
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        values = [json.loads(line) for line in first.read_text().splitlines()]
        self.assertEqual(values[0]["head"], rev)
        self.assertEqual(values[1]["id"], "w-source-1-1")
        self.assertEqual(values[1]["answers"], ["lib"])
        self.assertEqual(values[1]["files"], ["lib/thing.py"])
        self.assertEqual(values[2]["answers"], [])
        self.assertEqual(values[2]["files"], [])

    def test_written_preserves_backticked_spaces_and_hashes(self):
        self.write("AGENTS.md", "Read `my file.py` and `name#1.py`.\n")
        self.write("my file.py")
        self.write("name#1.py")
        rev = self.commit("initial")
        rows = self.input([{"question": "where is the implementation", "files": ["my file.py", "name#1.py"]}])
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(evalset.written(str(self.source), rev, str(rows)), 0)
        output = self.root / "state" / "eval" / "source-written-1-questions.jsonl"
        values = [json.loads(line) for line in output.read_text().splitlines()]
        self.assertEqual(values[1]["files"], ["my file.py", "name#1.py"])

    def test_written_refuses_leaks_and_untracked_without_creating_output(self):
        rev = self.routed_revision()
        cases = [{"question": "where is lib implementation", "files": ["lib/thing.py"]},
                 {"question": "where is thing.py implementation", "files": ["lib/thing.py"]},
                 {"question": "where is lib/thing.py implementation", "files": ["lib/thing.py"]},
                 {"question": "where is the implementation", "files": ["missing.py"]},
                 {"question": "where is the implementation", "files": ["lib/thing.py"] * 4}]
        for row in cases:
            with patch.dict(os.environ, self.env, clear=False), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(evalset.written(str(self.source), rev, str(self.input([row]))), 1)
        self.assertFalse((self.root / "state" / "eval").exists())

    def test_score_checks_floor_and_hand_edited_leak_before_any_request(self):
        rev = self.routed_revision()
        questions = self.root / "questions.jsonl"
        item = {"id": "old", "commit": rev, "parent": rev, "subject": "written",
                "question": "where is the implementation", "answers": ["lib"], "files": []}
        questions.write_text(json.dumps({"reviewed": True, "source": str(self.source.resolve()), "head": rev}) + "\n" + json.dumps(item) + "\n")
        with FakeDecisions({"lib": {"reach": 1, "own": .9}}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(evalset.score([str(questions)]), 1)
            self.assertEqual(fake.requests, [])
        item["question"] = "where is lib implementation"
        questions.write_text(json.dumps({"reviewed": True, "source": str(self.source.resolve()), "head": rev}) + "\n" + json.dumps(item) + "\n")
        with FakeDecisions({"lib": {"reach": 1, "own": .9}}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False), patch.object(evalset, "ANSWERABLE_FLOOR", 1), patch.object(evalset, "UNANSWERABLE_FLOOR", 0), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(evalset.score([str(questions)]), 1)
            self.assertEqual(fake.requests, [])

    def test_score_records_origin_and_repo_metrics_and_unanswerable_false_answers(self):
        rev = self.routed_revision()
        questions = self.root / "questions.jsonl"
        rows = []
        for number in range(40):
            rows.append({"id": "w-source-1-%d" % number, "commit": rev, "parent": rev,
                         "subject": "written", "question": "where is the implementation",
                         "answers": ["."], "files": []})
        for number in range(5):
            rows.append({"id": "w-source-1-u%d" % number, "commit": rev, "parent": rev,
                         "subject": "written", "question": "what should we do next now",
                         "answers": [], "files": []})
        questions.write_text(json.dumps({"reviewed": True, "source": str(self.source.resolve()), "head": rev}) + "\n" + "\n".join(json.dumps(row) for row in rows) + "\n")
        table = {".": {"reach": 1, "own": .99}, "lib": {"reach": .1, "own": .1}}
        with FakeDecisions(table) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(evalset.score([str(questions)]), 1)
        candidate = json.loads((self.root / "state" / "eval" / "bars.candidate.json").read_text())
        self.assertEqual(set(candidate["metrics"]), {"pool", "repos", "drafted", "written"})
        self.assertIn(str(self.source.resolve()), candidate["metrics"]["repos"])
        self.assertEqual(candidate["metrics"]["pool"]["false_answer_rate"], 1.0)
        self.assertEqual(candidate["metrics"]["written"]["answerable_questions"], 40)

    def test_selection_checks_new_limits_and_empty_drafted_report_passes(self):
        pool = {"answered_rate": .9, "top_wrong_rate": 0, "answer_precision": .9,
                "median_narrowing": .1, "false_answer_rate": 0}
        grouped = {"pool": pool, "drafted": {"top_wrong_rate": 0}}
        self.assertTrue(evalset._passes_selection(grouped))
        self.assertFalse(evalset._passes_selection({"pool": pool, "drafted": {"top_wrong_rate": .1}}))
        self.assertFalse(evalset._passes_selection({"pool": dict(pool, false_answer_rate=.1), "drafted": {"top_wrong_rate": 0}}))
        output = io.StringIO()
        metrics = {"pool": dict(pool, answered=1, recall=.9, unanswerable_questions=0, questions=1,
                                 answerable_questions=1, file_precision=0, file_recall=0, files_returned=0,
                                 false_answers=0), "repos": {},
                   "drafted": dict(pool, answered=0, recall=0, unanswerable_questions=0, questions=0,
                                   answerable_questions=0, file_precision=0, file_recall=0, files_returned=0,
                                   false_answers=0),
                   "written": dict(pool, answered=1, recall=.9, unanswerable_questions=0, questions=1,
                                   answerable_questions=1, file_precision=0, file_recall=0, files_returned=0,
                                   false_answers=0)}
        with contextlib.redirect_stdout(output):
            evalset._report("score", metrics, evalset._gates(metrics, {"file": None}))
        self.assertIn("no drafted question answered", output.getvalue())


class LeakWordBoundaryTests(unittest.TestCase):
    def test_file_name_matches_only_as_a_whole_word(self):
        import subprocess, tempfile
        repo = tempfile.mkdtemp()
        subprocess.run(["git", "init", "-q", repo], check=True)
        with open(os.path.join(repo, "doc"), "w") as handle:
            handle.write("x")
        subprocess.run(["git", "-C", repo, "add", "doc"], check=True)
        subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"], check=True)
        head = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
        from highways import evalset
        self.assertFalse(evalset._leaks(repo, head, "Where are the documents rendered?", []))
        self.assertTrue(evalset._leaks(repo, head, "Where is the doc written?", []))
