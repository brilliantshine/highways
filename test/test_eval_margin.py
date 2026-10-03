import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from highways import evalset


def record(own, answers=("child",), p=.9):
    return {"answers": list(answers), "files": ["child/a.py"], "tracked": ["x%d" % n for n in range(20)],
            "routers": [{"dir": "child", "parent": None, "reach": own, "own": own, "own_files": ["child/a.py"]}],
            "file_scores": {"child": [{"path": "child/a.py", "p": p}]}}


POOL = {"answered_rate": .47, "top_wrong_rate": 0, "answer_precision": .9, "median_narrowing": .1,
        "false_answer_rate": 0, "file_precision": 1, "files_returned": 1}
DRAFTED = {"top_wrong_rate": 0}


class MarginTests(unittest.TestCase):
    def test_45_percent_passes_selection_and_both_gates(self):
        grouped = {"pool": POOL, "drafted": DRAFTED}
        self.assertTrue(evalset._passes_selection(grouped))
        self.assertTrue(evalset._passes_selection({"pool": dict(POOL, answered_rate=.45), "drafted": DRAFTED}))
        self.assertFalse(evalset._passes_selection({"pool": dict(POOL, answered_rate=.44), "drafted": DRAFTED}))
        # score calls _gates(metrics, bars); latency calls it with latency and require_files
        self.assertTrue(evalset._gates(grouped, {"file": None})["answered_rate"])
        self.assertTrue(evalset._gates(grouped, {"file": .8}, latency=.5, require_files=True)["answered_rate"])
        self.assertFalse(evalset._gates({"pool": dict(POOL, answered_rate=.44)}, {"file": None})["answered_rate"])
        self.assertFalse(evalset._gates({"pool": dict(POOL, answered_rate=.44)}, {"file": .8}, latency=.5)["answered_rate"])

    def test_shift_clamps_and_does_not_mutate(self):
        low = evalset._shifted([record(.01, p=.01)], -.02)[0]
        high = evalset._shifted([record(.99, p=.99)], .02)[0]
        self.assertEqual(low["routers"][0]["reach"], 0.0)
        self.assertEqual(low["routers"][0]["own"], 0.0)
        self.assertEqual(low["file_scores"]["child"][0]["p"], 0.0)
        self.assertEqual(high["routers"][0]["reach"], 1.0)
        self.assertEqual(high["routers"][0]["own"], 1.0)
        self.assertEqual(high["file_scores"]["child"][0]["p"], 1.0)
        original = record(.5)
        shifted = evalset._shifted([original], .02)[0]
        self.assertEqual(original["routers"][0]["own"], .5)
        self.assertAlmostEqual(shifted["routers"][0]["own"], .52)

    def test_setting_that_fails_when_lowered_is_rejected(self):
        records = [record(.9) for _ in range(4)]
        best = evalset._best_for_mode(records, "flat")
        self.assertIsNotNone(best)
        # a .90 bar answers on the cached scores but not once they drop by .02
        self.assertEqual(evalset._metrics(records, dict(best[0], answer=.9))["answered_rate"], 1.0)
        self.assertEqual(evalset._metrics(evalset._shifted(records, -.02), dict(best[0], answer=.9))["answered_rate"], 0.0)
        self.assertEqual(best[0]["answer"], .85)
        self.assertEqual(best[1]["margin"], {"low": 1.0, "cached": 1.0, "high": 1.0})

    def test_setting_that_fails_when_raised_is_rejected(self):
        # the unanswerable question's router sits at .86; a bar of .85 answers it once raised, and
        # of .88 answers it when raised by .02, so only bars from .90 up qualify
        records = [record(.95) for _ in range(6)] + [record(.86, answers=())]
        best = evalset._best_for_mode(records, "flat")
        self.assertIsNotNone(best)
        self.assertEqual(best[0]["answer"], .90)

    def test_no_setting_qualifies_when_none_survives_the_margin(self):
        self.assertIsNone(evalset._best_for_mode([record(.5)], "flat"))

    def test_score_fails_when_no_mode_survives_margin_even_if_fallback_gates_pass(self):
        # The .95 bar passes on cached scores, but its lowered margin does not;
        # every lower bar admits the unanswerable router and fails its false-answer gate.
        records = [record(.95) for _ in range(6)] + [record(.93, answers=())]
        self.assertIsNone(evalset._best_for_mode(records, "walk"))
        self.assertIsNone(evalset._best_for_mode(records, "flat"))
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            source = str(state / "fixture")
            questions = [{"id": str(index), "parent": str(index), "question": "q%d" % index,
                          "answers": value["answers"], "files": value["files"]}
                         for index, value in enumerate(records)]
            groups = [("questions.jsonl", {"source": source}, questions)]
            temporary = Mock()
            scored = [(value, 0) for value in records]
            with patch.dict(os.environ, {"HIGHWAYS_STATE": str(state)}, clear=False), \
                 patch.object(evalset, "_reviewed", return_value=groups), \
                 patch.object(evalset, "_floor_and_leaks", return_value=[]), \
                 patch.object(evalset, "_clone", return_value=(temporary, state)), \
                 patch.object(evalset, "_score_question", side_effect=scored), \
                 patch.object(evalset, "_report"):
                self.assertEqual(evalset.score([]), 1)
            candidate = json.loads((state / "eval" / "bars.candidate.json").read_text())
        self.assertFalse(candidate["passed"])
        self.assertTrue(all(candidate["gates"].values()))

    def test_ranking_prefers_worst_case_over_cached(self):
        a = {"answer": .5, "walk": .5}
        b = {"answer": .4, "walk": .4}
        self.assertGreater(evalset._selection_key((.6, .7, .7), b), evalset._selection_key((.5, .9, .9), a))
        self.assertGreater(evalset._selection_key((.5, .9, .9), b), evalset._selection_key((.5, .8, .9), a))
        self.assertGreater(evalset._selection_key((.5, .9, .9), a), evalset._selection_key((.5, .9, .9), b))

    def test_sweep_picks_higher_worst_case_over_higher_bar(self):
        records = [record(.95)]
        real = evalset._metric_groups

        def fake(rs, bars):
            groups = real(rs, bars)
            # in the lowered copy the top bar (.85 here is the highest that survives) answers less
            if rs[0]["routers"][0]["own"] < .95 and bars["answer"] == .90:
                groups["pool"] = dict(groups["pool"], answered_rate=.46)
            return groups
        with patch.object(evalset, "_metric_groups", fake):
            best = evalset._best_for_mode(records, "flat")
        self.assertEqual(best[0]["answer"], .85)
        self.assertEqual(best[1]["margin"], {"low": 1.0, "cached": 1.0, "high": 1.0})
        # without the patch the higher bar wins on the tie
        self.assertEqual(evalset._best_for_mode(records, "flat")[0]["answer"], .90)


if __name__ == "__main__":
    unittest.main()
