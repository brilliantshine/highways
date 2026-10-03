import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from highways import eval_review


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        (self.source / "a.py").write_text("one\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "first commit")
        self.c1 = self.git("rev-parse", "HEAD").strip()
        (self.source / "a.py").write_text("two\n")
        (self.source / "b.py").write_text("new\n")
        (self.source / ".gitignore").write_text("ignored.txt\n")
        (self.source / "ignored.txt").write_text("x\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "second commit\n\nbody text here")
        self.c2 = self.git("rev-parse", "HEAD").strip()
        self.before = self.status()
        self.rows = [
            {"id": self.c1, "commit": self.c1, "parent": self.c1, "subject": "first commit", "question": "first commit", "answers": ["."], "files": []},
            {"id": self.c2, "commit": self.c2, "parent": self.c1, "subject": "second commit", "question": "second commit", "answers": ["."], "files": ["b.py"], "proposed": "where is the code that seconds", "suggest": "keep", "why": "clear"},
            {"id": "x" * 40, "commit": "f" * 40, "parent": self.c1, "subject": "third", "question": "third", "answers": [], "files": [], "suggest": "drop"},
        ]
        self.file = self.root / "q.jsonl"
        header = {"reviewed": False, "source": str(self.source), "head": self.c2}
        self.file.write_text(json.dumps(header) + "\n" + "".join(json.dumps(row, sort_keys=True) + "\n" for row in self.rows))
        self.server = eval_review.make_server([str(self.file)])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:%d/highways-review" % self.server.server_address[1]
        self.t = self.server.token

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp.cleanup()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.source), *args], text=True)

    def status(self):
        return self.git("status", "--porcelain", "--ignored")

    def req(self, path, body=None, token=True):
        url = self.base + path
        if token:
            url += ("&" if "?" in url else "?") + "t=" + self.t
        data = json.dumps(body).encode() if body is not None else None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data)) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def decide(self, qid, **fields):
        return self.req("/api/decide", dict(file=0, id=qid, **fields))

    def lines(self):
        return self.file.read_text().splitlines()

    def test_token_and_prefix(self):
        self.assertEqual(self.req("/", token=False)[0], 403)
        self.assertEqual(self.req("/api/state?file=0&t=wrong", token=False)[0], 403)
        status, body = self.req("/")
        self.assertEqual(status, 200)
        self.assertIn(b"Review questions", body)
        outside = "http://127.0.0.1:%d/other/?t=%s" % (self.server.server_address[1], self.t)
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(outside)
        self.assertEqual(caught.exception.code, 404)
        self.assertIn("/highways-review/?t=" + self.t, self.server.url)

    def test_save_decision_leaves_other_lines(self):
        before = self.lines()
        status, body = self.decide(self.c2, review="keep", edited="where is the code that does two")
        self.assertEqual(status, 200)
        after = self.lines()
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])
        self.assertEqual(before[3], after[3])
        saved = json.loads(after[2])
        self.assertEqual((saved["review"], saved["edited"], saved["question"]), ("keep", "where is the code that does two", "second commit"))
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".review")], [])
        state = json.loads(self.req("/api/state?file=0")[1])
        self.assertEqual(state["questions"][1]["review"], "keep")

    def edit(self, qid, **fields):
        return self.req("/api/edit", dict(file=0, id=qid, **fields))

    def test_edit_keeps_decision(self):
        self.decide(self.c1, review="keep")
        before = self.lines()
        self.assertEqual(self.edit(self.c1, edited="better")[0], 200)
        after = self.lines()
        self.assertEqual([before[0], before[2], before[3]], [after[0], after[2], after[3]])
        self.assertEqual(json.loads(after[1])["review"], "keep")
        self.assertEqual(json.loads(after[1])["edited"], "better")
        self.assertEqual(self.edit(self.c2, edited="where is two")[0], 200)
        saved = json.loads(self.lines()[2])
        self.assertNotIn("review", saved)
        self.assertEqual(saved["edited"], "where is two")
        self.assertEqual(self.edit(self.c2)[0], 400)
        self.assertEqual(self.edit("nope", edited="x")[0], 404)

    def test_edit_refused_when_finished(self):
        self.decide(self.c1, review="drop")
        self.decide(self.c2, review="keep")
        self.decide("x" * 40, review="drop")
        self.edit(self.c2, edited="saved edit")
        self.assertEqual(self.req("/api/finish", {"file": 0})[0], 200)
        done = self.file.read_text()
        self.assertEqual(self.edit(self.c2, edited="late")[0], 409)
        self.assertEqual(self.file.read_text(), done)
        self.assertEqual(json.loads(self.lines()[1])["question"], "saved edit")

    def test_commit_details(self):
        status, body = self.req("/api/commit?file=0&id=" + self.c2)
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertIn("body text here", value["message"])
        self.assertIn(["A", "b.py"], value["changed"])
        self.assertEqual(self.req("/api/commit?file=0&id=" + "a" * 40)[0], 404)
        self.assertEqual(self.req("/api/commit?file=0&id=--help")[0], 404)

    def test_finish(self):
        original = self.file.read_text()
        self.assertEqual(self.req("/api/finish", {"file": 0})[0], 409)
        self.assertEqual(self.file.read_text(), original)
        self.decide(self.c1, review="drop")
        self.decide(self.c2, review="keep", edited="where is the code that does two")
        self.decide("x" * 40, review="keep")
        status, _ = self.req("/api/finish", {"file": 0})
        self.assertEqual(status, 200)
        lines = self.lines()
        self.assertEqual(json.loads(lines[0]), {"reviewed": True, "source": str(self.source), "head": self.c2})
        kept = [json.loads(line) for line in lines[1:]]
        self.assertEqual([item["id"] for item in kept], [self.c2, "x" * 40])
        self.assertEqual(kept[0]["question"], "where is the code that does two")
        self.assertEqual(kept[0]["subject"], "second commit")
        self.assertEqual(kept[1]["question"], "third")
        for item in kept:
            for key in ("review", "edited", "proposed", "suggest", "why"):
                self.assertNotIn(key, item)
        backup = Path(str(self.file) + ".pre-review.bak")
        saved = [json.loads(line) for line in backup.read_text().splitlines()]
        self.assertFalse(saved[0]["reviewed"])
        self.assertEqual([item["review"] for item in saved[1:]], ["drop", "keep", "keep"])
        self.assertEqual(self.decide(self.c2, review="drop")[0], 409)
        self.assertEqual(self.status(), self.before)

    def test_refuses_reviewed_file(self):
        done = self.root / "done.jsonl"
        done.write_text(json.dumps({"reviewed": True, "source": "x", "head": "y"}) + "\n")
        with self.assertRaises(ValueError):
            eval_review.QuestionFile(str(done))

    def test_source_untouched(self):
        self.req("/api/commit?file=0&id=" + self.c1)
        self.decide(self.c1, review="keep", edited="q")
        self.assertEqual(self.status(), self.before)


if __name__ == "__main__":
    unittest.main()
