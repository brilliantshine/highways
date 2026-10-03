import hashlib
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


class EvalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "test")
        self.state = self.root / "state"
        self.config = self.root / "person-config.json"
        self.env = {"HIGHWAYS_STATE": str(self.state), "HIGHWAYS_CONFIG": str(self.config),
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

    def starter(self):
        self.write("AGENTS.md", "Read `lib/code.py`.\n")
        self.write("lib/code.py")
        return self.commit("initial")

    def questions(self, reviewed=True, question="where is code", answers=None, files=None):
        parent = self.git("rev-parse", "HEAD")
        item = {"id": parent, "commit": parent, "parent": parent, "subject": question,
                "question": question, "answers": answers or ["."], "files": files or []}
        path = self.root / "questions.jsonl"
        path.write_text(json.dumps({"reviewed": reviewed, "source": str(self.source.resolve()), "head": parent}) + "\n" + json.dumps(item) + "\n")
        return path, item

    def test_prefix_stripping(self):
        self.assertEqual(evalset._question("ABC-123: fix(api): change cache"), "change cache")
        self.assertEqual(evalset._question("fix: BE-2: improve thing"), "improve thing")

    def test_draft_qualifies_only_routed_non_markdown_non_router_changes(self):
        self.starter()
        self.write("lib/code.py", "valid\n")
        good = self.commit("ABC-123: fix(api): change code")
        self.write("docs/guide.py")
        self.commit("docs only")
        self.write("lib/readme.md")
        self.commit("markdown only")
        self.write("lib/AGENTS.md")
        self.commit("router touch")
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(evalset.draft(str(self.source)), 0)
        drafted = self.state / "eval" / "source-questions.jsonl"
        lines = [json.loads(line) for line in drafted.read_text().splitlines()]
        self.assertEqual(lines[0], {"reviewed": False, "source": str(self.source.resolve()), "head": self.git("rev-parse", "HEAD")})
        found = [item for item in lines[1:] if item["commit"] == good]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["question"], "change code")
        self.assertEqual(found[0]["files"], ["lib/code.py"])

    def test_covering_rejects_zero_and_six_directories(self):
        self.assertIsNone(evalset._covering([], "a.py"))
        routers = [evalset.Router("d%d" % number, (), "", None) for number in range(6)]
        covered = [evalset._covering(routers, "d%d/a.py" % number) for number in range(6)]
        self.assertEqual(len({router.dir for router in covered if router}), 6)

    def test_draft_refuses_reviewed_file_and_never_changes_source(self):
        self.starter()
        self.write("lib/code.py", "changed\n")
        self.commit("fix: code")
        before = self.git_state()
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(evalset.draft(str(self.source)), 0)
        path = self.state / "eval" / "source-questions.jsonl"
        rows = path.read_text().splitlines()
        header = json.loads(rows[0])
        header["reviewed"] = True
        path.write_text(json.dumps(header) + "\n" + "\n".join(rows[1:]) + "\n")
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(evalset.draft(str(self.source)), 1)
        self.assertEqual(before, self.git_state())

    def test_score_refuses_unreviewed_and_caches_requests(self):
        self.starter()
        questions, item = self.questions(reviewed=False, files=["lib/code.py"])
        with patch.dict(os.environ, self.env, clear=False):
            self.assertEqual(evalset.score([str(questions)]), 1)
        header = json.loads(questions.read_text().splitlines()[0])
        header["reviewed"] = True
        questions.write_text(json.dumps(header) + "\n" + json.dumps(item) + "\n")
        before = self.git_state()
        with FakeDecisions({".": {"reach": 1, "own": .9, "files": [.9]}}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False), patch.object(evalset, "ANSWERABLE_FLOOR", 1), patch.object(evalset, "UNANSWERABLE_FLOOR", 0):
            evalset.score([str(questions)])
            first = len(fake.requests)
            evalset.score([str(questions)])
            self.assertEqual(len(fake.requests), first)
        self.assertGreater(first, 0)
        self.assertEqual(before, self.git_state())

    def test_sweep_prefers_flat_on_tie_and_can_disable_file_step(self):
        record = {"answers": ["child"], "files": ["child/a.py"], "tracked": ["x%d" % n for n in range(20)],
                  "routers": [{"dir": "child", "parent": None, "reach": .9, "own": .9,
                               "own_files": ["child/a.py"]}], "file_scores": {"child": [{"path": "child/a.py", "p": .4}]}}
        self.assertIsNotNone(evalset._best_for_mode([record], "walk"))
        flat = evalset._best_for_mode([record], "flat")
        self.assertIsNotNone(flat)
        self.assertEqual(flat[0]["mode"], "flat")
        self.assertIsNone(evalset._choose_file([record], flat[0]))

    def test_latency_uses_child_config_and_only_copies_bars_on_pass(self):
        self.write("AGENTS.md", "root\n")
        self.write("child/AGENTS.md", "Read `code.py`.\n")
        self.write("child/code.py")
        for number in range(12):
            self.write("other%d.txt" % number)
        self.commit("initial")
        questions, item = self.questions(answers=["child"], files=["child/code.py"])
        self.config.write_text("person config stays here")
        candidate = {"walk": .5, "answer": .7, "file": .8, "cap": 5, "mode": "flat", "passed": True}
        candidate_path = self.state / "eval" / "bars.candidate.json"
        candidate_path.parent.mkdir(parents=True)
        candidate_path.write_text(json.dumps(candidate))
        shipped_bars = ROOT / "search" / "bars.json"
        shipped_before = (shipped_bars.read_bytes(), shipped_bars.stat().st_mode)
        bars = self.root / "published-bars.json"
        before = self.git_state()
        table = {".": {"reach": 1, "own": .1}, "child": {"reach": 1, "own": .9, "files": [.9]}}
        with FakeDecisions(table) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url, "HIGHWAYS_BARS_TARGET": str(bars)}, clear=False):
            self.assertEqual(evalset.latency([str(questions)]), 0)
        self.assertEqual(self.config.read_text(), "person config stays here")
        self.assertEqual(json.loads(bars.read_text()), {key: candidate[key] for key in evalset.BAR_KEYS})
        with FakeDecisions({".": {"reach": 1, "own": .1}, "child": {"reach": 1, "own": .1}}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url, "HIGHWAYS_BARS_TARGET": str(bars)}, clear=False):
            self.assertEqual(evalset.latency([str(questions)]), 1)
        self.assertEqual(json.loads(bars.read_text()), {key: candidate[key] for key in evalset.BAR_KEYS})
        self.assertEqual((shipped_bars.read_bytes(), shipped_bars.stat().st_mode), shipped_before)
        self.assertEqual(before, self.git_state())

    def git_state(self):
        status = self.git("--no-optional-locks", "status", "--porcelain", "--ignored")
        tree = {}
        for path in (self.source / ".git").rglob("*"):
            if path.is_file():
                tree[str(path.relative_to(self.source))] = hashlib.sha256(path.read_bytes()).hexdigest()
        return status, tree
