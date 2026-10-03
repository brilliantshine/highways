import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from helpers import FakeDecisions

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT))
from highways import search as search_module
from highways.routers import discover


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.config = Path(self.temp.name) / "config.json"
        # Tests pin their own bars, so the shipped search/bars.json can change without touching them.
        self.bars_file = Path(self.temp.name) / "bars.json"
        self.bars_file.write_text('{"walk": 0.5, "answer": 0.7, "file": 0.85, "cap": 5, "mode": "walk"}')
        self.env = {"HIGHWAYS_CONFIG": str(self.config), "OPENROUTER_API_KEY": "test-key", "HIGHWAYS_BARS": str(self.bars_file)}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, text="router"):
        target = self.repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def enable(self):
        self.config.write_text(json.dumps({"default": "off", "repos": {str(self.repo.resolve()): "on"}}))

    def call(self, table, bars=None, question="where is it"):
        self.enable()
        with FakeDecisions(table) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False):
            value = search_module.search(str(self.repo), question, bars=bars)
        return value, fake

    @staticmethod
    def bars(**changes):
        base = {"walk": .5, "answer": .7, "file": None, "cap": 5, "mode": "walk"}
        base.update(changes)
        return base

    def test_root_is_answer_and_real_cli_json(self):
        self.write("AGENTS.md")
        self.enable()
        with FakeDecisions({".": {"reach": .1, "own": .9}}) as fake:
            env = os.environ | self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}
            result = subprocess.run([str(ROOT / "bin/highways"), "search", "where is it", "--repo", str(self.repo), "--json"], env=env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["answers"][0]["dir"], ".")
        self.assertEqual(len(fake.requests), 1)

    def test_child_answer(self):
        self.write("AGENTS.md")
        self.write("child/AGENTS.md")
        value, _ = self.call({".": {"reach": .2, "own": .1}, "child": {"reach": .8, "own": .9}})
        self.assertEqual([item["dir"] for item in value["answers"]], ["child"])

    def test_discovery_skips_router_inside_nested_repo_even_when_outer_tracks_it(self):
        self.write("AGENTS.md")
        vendor = self.repo / "vendor"
        subprocess.run(["git", "init", "-q", str(vendor)], check=True)
        self.write("vendor/AGENTS.md", "nested router")
        subprocess.run(["git", "-C", str(self.repo), "add", "-f", "vendor/AGENTS.md"], check=True)
        self.assertNotIn("vendor", {router.dir for router in discover(str(self.repo))})

    def test_weak_parent_hides_child(self):
        self.write("AGENTS.md")
        self.write("parent/AGENTS.md")
        self.write("parent/child/AGENTS.md")
        value, _ = self.call({".": {"reach": 1, "own": 0}, "parent": {"reach": .2, "own": 0}, "parent/child": {"reach": 1, "own": 1}})
        self.assertEqual(value["status"], "not-confident")

    def test_flat_skips_walk(self):
        self.write("AGENTS.md")
        self.write("child/AGENTS.md")
        value, _ = self.call({".": {"reach": 0, "own": .8}, "child": {"reach": 0, "own": .9}}, self.bars(mode="flat"))
        self.assertEqual([item["dir"] for item in value["answers"]], ["child", "."])

    def test_not_confident(self):
        self.write("AGENTS.md")
        value, _ = self.call({".": {"reach": 1, "own": .2}})
        self.assertEqual(value["status"], "not-confident")
        self.assertIn("grep", value["note"])

    def test_failure_is_unavailable(self):
        self.write("AGENTS.md")
        self.write("child/AGENTS.md")
        value, _ = self.call({".": {"reach": 1, "own": 1}, "child": {"fail": True}})
        self.assertEqual(value["status"], "unavailable")

    def test_slow_router_is_resent_once_and_uses_second_answer(self):
        self.write("AGENTS.md")
        value, fake = self.call({".": {"attempts": [{"sleep": .5}, {"reach": 1, "own": .9}]}})
        self.assertEqual(value["status"], "answers")
        self.assertEqual(len(fake.requests), 2)
        self.assertTrue(all(body["provider"] == {"zdr": True} for body in fake.requests))

    def test_late_failed_resend_never_replaces_a_valid_first_answer(self):
        self.write("AGENTS.md")
        self.write("lib/AGENTS.md")
        value, fake = self.call({
            ".": {"attempts": [{"sleep": .4, "reach": 1, "own": .9}, {"sleep": .1, "fail": True}]},
            "lib": {"sleep": .6, "reach": 1, "own": .9},
        })
        self.assertEqual(value["status"], "answers")

    def test_failed_router_is_resent_promptly(self):
        self.write("AGENTS.md")
        value, fake = self.call({".": {"attempts": [{"fail": True}, {"reach": 1, "own": .9}]}})
        self.assertEqual(value["status"], "answers")
        self.assertEqual(len(fake.requests), 2)
        self.assertLessEqual(fake.request_times[1] - fake.request_times[0], .35)

    def test_two_slow_router_attempts_are_unavailable_without_third_send(self):
        self.write("AGENTS.md")
        value, fake = self.call({".": {"attempts": [{"sleep": 1}, {"sleep": 1}]}})
        self.assertEqual(value["status"], "unavailable")
        self.assertEqual(len(fake.requests), 2)

    def test_quick_router_answer_is_not_resent(self):
        self.write("AGENTS.md")
        value, fake = self.call({".": {"reach": 1, "own": .9}})
        self.assertEqual(value["status"], "answers")
        self.assertEqual(len(fake.requests), 1)

    def test_file_step_and_unbudgeted_score_never_resend(self):
        self.write("AGENTS.md", "Read `live.py`.")
        self.write("live.py", "x")
        self.enable()
        table = {".": {"attempts": [
            {"reach": 1, "own": .9}, {"sleep": .5, "files": [.9]},
        ]}}
        with FakeDecisions(table) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False):
            value = search_module.search(str(self.repo), "where", bars=self.bars(file=.85))
        self.assertEqual(value["status"], "answers")
        self.assertEqual(len(fake.requests), 2)

        routers = discover(str(self.repo))
        with FakeDecisions({".": {"sleep": .1}}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False):
            with self.assertRaises(search_module.Unavailable):
                search_module.score_routers(str(self.repo), routers, "where", budget=None, timeout=.01)
        self.assertEqual(len(fake.requests), 1)

    def test_cli_exits_at_round_budget_when_router_never_answers(self):
        self.write("AGENTS.md")
        self.enable()
        with FakeDecisions({".": {"sleep": 2}}) as fake:
            started = time.monotonic()
            result = subprocess.run([str(ROOT / "bin/highways"), "search", "where", "--repo", str(self.repo), "--json"],
                                    env=os.environ | self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, text=True,
                                    capture_output=True, check=False, timeout=1)
            elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0)
        self.assertLess(elapsed, .9)
        self.assertEqual(json.loads(result.stdout)["status"], "unavailable")

    def test_off_and_no_routers_send_nothing(self):
        self.write("AGENTS.md")
        with FakeDecisions({".": {"reach": 1, "own": 1}}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False):
            value = search_module.search(str(self.repo), "where")
        self.assertEqual(value["status"], "not-enabled")
        self.assertEqual(fake.requests, [])
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        subprocess.run(["git", "init", "-q", str(empty)], check=True)
        self.enable()
        with FakeDecisions({}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False):
            value = search_module.search(str(empty), "where")
        self.assertEqual(value["status"], "no-routers")
        self.assertEqual(fake.requests, [])

    def test_zdr_and_file_step_only_existing_named_files(self):
        self.write("AGENTS.md", "Read `live.py`, `gone.py`, and [linked](docs/a.txt).")
        self.write("live.py", "x")
        self.write("docs/a.txt", "x")
        value, fake = self.call({".": {"reach": 1, "own": .9, "files": [.9, .6]}}, self.bars(file=.85))
        self.assertEqual(value["answers"][0]["files"], [{"path": "live.py", "p": .9}])
        self.assertTrue(all(body["provider"] == {"zdr": True} for body in fake.requests))
        self.assertEqual(len(fake.requests), 2)
        file_questions = fake.requests[1]["questions"]
        self.assertIn("`live.py`", file_questions["f0"]["instructions"])
        self.assertNotIn("files", fake.requests[1]["state"])

    def test_named_files_preserves_backticked_spaces_and_hashes(self):
        self.write("AGENTS.md", 'Read `my file.py`, `name#1.py`, [x](docs/a.md#part), and [t](docs/title.md "title").')
        self.write("my file.py", "x")
        self.write("name#1.py", "x")
        self.write("docs/a.md", "x")
        self.write("docs/title.md", "x")
        self.assertEqual(search_module.named_files(str(self.repo), discover(str(self.repo))[0]),
                         ["my file.py", "name#1.py", "docs/a.md", "docs/title.md"])

    def test_malformed_config_disables_search(self):
        self.write("AGENTS.md")
        malformed = (
            {"default": "on", "repos": []},
            {"default": "on", "repos": {str(self.repo.resolve()): "Off"}},
            {"default": "on", "repos": {str(self.repo.resolve()): ["on"]}},
            {"default": []},
            {"default": "ON"},
        )
        for value in malformed:
            self.config.write_text(json.dumps(value))
            with self.subTest(value=value), FakeDecisions({".": {"reach": 1, "own": 1}}) as fake:
                result = subprocess.run([str(ROOT / "bin/highways"), "search", "where", "--repo", str(self.repo), "--json"],
                                        env=os.environ | self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, text=True,
                                        capture_output=True, check=False)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(json.loads(result.stdout)["status"], "not-enabled")
            self.assertEqual(fake.requests, [])

    def test_well_formed_repo_config_still_sends(self):
        self.write("AGENTS.md")
        self.config.write_text(json.dumps({"default": "off", "repos": {str(self.repo.resolve()): "on"}}))
        with FakeDecisions({".": {"reach": 1, "own": 1}}) as fake:
            result = subprocess.run([str(ROOT / "bin/highways"), "search", "where", "--repo", str(self.repo), "--json"],
                                    env=os.environ | self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, text=True,
                                    capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["status"], "answers")
        self.assertEqual(len(fake.requests), 1)

    def test_cap_of_five(self):
        for number in range(6):
            self.write("d%d/AGENTS.md" % number)
        table = {"d%d" % number: {"reach": 1, "own": .9} for number in range(6)}
        value, _ = self.call(table)
        self.assertEqual(len(value["answers"]), 5)

    def test_symlink_pair_is_one_router_and_search_does_not_change_repo(self):
        self.write("AGENTS.md", "root")
        os.symlink("AGENTS.md", self.repo / "CLAUDE.md")
        before = hashlib.sha256((self.repo / "AGENTS.md").read_bytes()).hexdigest()
        tree_before = self.tree_state()
        self.assertEqual(len(discover(str(self.repo))), 1)
        value, _ = self.call({".": {"reach": 1, "own": .9}})
        self.assertEqual(value["status"], "answers")
        self.assertEqual(before, hashlib.sha256((self.repo / "AGENTS.md").read_bytes()).hexdigest())
        self.assertEqual(tree_before, self.tree_state())

    def tree_state(self):
        files = {}
        for path in sorted(self.repo.rglob("*")):
            if path.is_file() and not path.is_symlink():
                files[str(path.relative_to(self.repo))] = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
        status = subprocess.check_output(["git", "--no-optional-locks", "-C", str(self.repo), "status", "--porcelain", "--ignored"])
        return files, status

    def test_router_link_outside_repo_is_never_read_or_sent(self):
        outside = Path(tempfile.mkdtemp()) / "secret.md"
        outside.write_text("outside-secret")
        self.write("AGENTS.md", "root")
        os.makedirs(self.repo / "lib")
        os.symlink(outside, self.repo / "lib" / "AGENTS.md")
        self.write("pkg/AGENTS.md", "pkg router")
        os.symlink(outside, self.repo / "pkg" / "CLAUDE.md")
        routers = {router.dir: router for router in discover(str(self.repo))}
        self.assertNotIn("lib", routers)
        self.assertEqual(routers["pkg"].text, "pkg router")
        value, fake = self.call({".": {"reach": 1, "own": .9}, "pkg": {"reach": 1, "own": .9}})
        self.assertFalse(any("outside-secret" in json.dumps(body) for body in fake.requests))

    def test_bad_bars_are_unavailable(self):
        self.write("AGENTS.md")
        self.enable()
        self.bars_file.write_text('{"walk": 0.5, "answer": 0.9, "file": 0.8, "cap": 5, "mode": "walk"}')
        with FakeDecisions({}) as fake, patch.dict(os.environ, self.env | {"HIGHWAYS_DECISIONS_URL": fake.url}, clear=False):
            value = search_module.search(str(self.repo), "where")
        self.assertEqual(value["status"], "unavailable")
        self.assertIn("bars", value["note"])
        self.assertEqual(fake.requests, [])

    def test_enable_refuses_without_terminal_and_outside_repo_is_one(self):
        result = subprocess.run([str(ROOT / "bin/highways"), "enable", str(self.repo)], env=os.environ | self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.config.exists())
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        result = subprocess.run([str(ROOT / "bin/highways"), "search", "where", "--repo", str(outside)], env=os.environ | self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 1)
