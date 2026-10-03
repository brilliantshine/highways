# Remediation 1 — router-search

Verification round 1, 2026-10-03. Verifiers: Claude default reviewer model (checks the GPT
lanes' work) and GPT / Sol `gpt-6.1-sol`, thread `01a103d8-c0dd-7fd3-ba93-f05cd8ef0d69` (checks
the Claude lanes' work). Both: `VERDICT: FAIL`.

## Gap list (verbatim)

Claude verifier:

```
GAP: Routers (wheelchair root `AGENTS.md`, "Maintaining these routers") — commit `31cd143` removed the "updates the routers on both sides" rule from `protocol/implementation.md:218-223`, but the root router still says "Stage 3 states that rule where an implementer will meet it". Stage 3 now only says to run `highways sweep` and apply highways' `protocol/sweep.md`, and with highways absent it skips the sweep entirely. So the router now claims something the change made false, and COMPLETION's Routers section doesn't mention it — wheelchair `AGENTS.md:139-142` against wheelchair `protocol/implementation.md:221-224`.
GAP: Test set, D50 ("until then the working tree's file keeps its previous values"), and the highways root router's claim that `search/bars.json` is "set only by a passing test-set run" — `test/test_eval.py:148-165` (`test_latency_uses_child_config_and_only_copies_bars_on_pass`) overwrites the shipped `search/bars.json` with `{answer 0.7, file 0.8}` and restores it only in a `finally`. The real install links `~/.local/bin/highways` to this checkout, so any live hook search during `python3 -m unittest discover -s test` uses bars below the measured ones, and a killed run leaves the file changed. Evidence: after my unittest run the file's mtime moved to 15:19 (the commit was 15:00) and its mode is now 0600, with the content restored. `test_search.py` was fixed to use `HIGHWAYS_BARS`; this test wasn't.
```

GPT / Sol verifier:

```
GAP: Search step 1 — Discovery includes routers inside nested git repositories, contrary to the scanner's exclusion rules — routers.py:28; a temp fixture returned `vendor/AGENTS.md` while the scanner excluded `vendor`.
GAP: Bar selection, D64–D67 — Scoring can approve fallback bars when no setting passes the ±0.02 margin — evalset.py:645; reproduced both modes returning no qualifying setting, followed by exit 0 and `passed: true`, `margin: null`.
GAP: Wheelchair removal — Cleanup can recursively delete an unrelated `spine` skill merely because it mentions its own `spine.md` — install.sh:71; executing the isolated cleanup function against a temp foreign plugin deleted it.
GAP: Snapshot and upkeep, D33 — Hashing follows symlinks, missing retargets between identical-content files; a broken symlink also suppresses upkeep for unrelated changes — snapshot.py:55; reproduced an empty changed-path set after retargeting, then sweep exit 1 and a silent Stop hook with changed code present.
GAP: Search step 2 — Malformed configuration structures crash instead of falling back to sending off — config.py:21; `{"default":[]}` produced `TypeError`, CLI exit 1, and no search result.
GAP: Search step 7 — Existing files explicitly named in backticks are dropped when their names contain spaces or `#` — search.py:93; `my file.py` and `name#1.py` each produced an empty named-file list.
GAP: Git constraint, D40 / Routers accuracy — The scanner runs git without `--no-optional-locks`, contradicting the spec and highways' root router — scan.sh:27, scan.sh:407, AGENTS.md:62.
GAP: Phase 6 validation — The mandatory viewer suite does not pass — validation log: 132 passes, one failure at `lifecycle.test.js:449`; independently reproduced on an archive of unchanged `main` (`a552802`), confirming it predates this change.
```

## Tasks

Routed to the family that built each piece (lanes.md continuation rules). Round 1 sharpens the
brief; no tier change.

| # | Gap | Fix | Owner | Lane |
|---|-----|-----|-------|------|
| M1 | Nested repos in discovery | `highways/routers.py`: drop a router whose path passes through a directory (below the repo root) holding a `.git` entry; test with a nested repo fixture whose files are also tracked by the outer repo | `highways/routers.py`, `test/test_search.py` | Terra (gpt-5.6-terra) |
| M2 | Fallback bars pass | `highways/evalset.py` `score`: when neither mode has a qualifying setting, the candidate's `passed` is false and `score` exits 1, whatever the fallback's gates say; test it | `highways/evalset.py`, `test/test_eval_margin.py` | Terra |
| M3 | Snapshot follows symlinks; broken link silences upkeep | `highways/snapshot.py`: a symlink's recorded value is `link:` plus its target text (`os.readlink`), never its target's content; anything that can't be read hashes to a fixed marker instead of raising; tests for a retarget between identical files and a broken link beside a real change | `highways/snapshot.py`, `test/hooks.sh` | Terra |
| M4 | Malformed config crashes | `highways/config.py` `read`: any structural surprise (non-string `default`, non-dict `repos`, non-string keys or values) counts as `{"default": "off"}` / drops the entry; catch `TypeError`; tests | `highways/config.py`, `test/test_search.py` | Terra |
| M5 | Backticked names with spaces or `#` dropped | `highways/search.py` `named_files`: a backticked token is taken whole (no split, no `#` stripping); a markdown link target drops only a trailing `"title"` and an `#anchor`; tests | `highways/search.py`, `test/test_search.py` | Terra |
| M6 | Latency test overwrites shipped bars | `highways/evalset.py` `latency` writes to `$HIGHWAYS_BARS_TARGET` when set (test seam), else `search/bars.json`; `test/test_eval.py` uses the seam and never touches the shipped file | `highways/evalset.py`, `test/test_eval.py` | Terra |
| M7 | Scanner git calls | Both calls in `create/scan.sh` pass `--no-optional-locks` | `create/scan.sh` | lead — done: 80 passed |
| M8 | Wheelchair root router stale | Wheelchair `AGENTS.md` "Maintaining these routers": the rule now lives in highways' `protocol/sweep.md`; factual correction only | wheelchair `AGENTS.md` | Claude / Sonnet |
| M9 | Wheelchair cleanup too broad | Wheelchair `install.sh` `remove_rendered_retired`: remove only when the rendered file names this checkout's own `$ROOT/protocol/spine.md` path; suite case for a foreign `spine` skill that mentions some other `spine.md` | wheelchair `install.sh`, `install/test/run.sh` | Claude / Sonnet |
| — | Viewer suite failure | Not fixed here: fails identically on unchanged `main` (`a552802`), outside this plan's scope. Raised with Collin | — | — |
