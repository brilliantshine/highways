# Remediation 2 — router-search

Verification round 2 (closure review), 2026-10-03. Claude default reviewer model: `VERDICT: PASS`.
GPT / Sol `gpt-6.1-sol` (thread `01a103d8-c0dd-7fd3-ba93-f05cd8ef0d69`, resumed): `VERDICT: FAIL`.

## Gap list (verbatim)

```
GAP: M4 / Search step 2 — Malformed configuration can still permit sending — config.py:23; `{"default":"on","repos":[]}` became default-on, and an independent fake-server search sent one request instead of returning `not-enabled`.
GAP: M5 / Test-set file labels — Historical filename parsing still drops spaces and `#`, contradicting the corrected search parser — evalset.py:154; in a pinned temp commit, production recognized `my file.py` and `name#1.py`, but `eval written` recorded `files: []`.
```

## Tasks

M4 survived round 1, and the cause was the round-1 brief: it told the lane to keep a valid
`default` while dropping a malformed `repos`. Round 2 rewrites the rule to fail closed and, per
lanes.md, runs a fresh Terra lane at `xhigh` (nearly-right work that missed an edge case).

| # | Gap | Fix | Owner | Lane |
|---|-----|-----|-------|------|
| N1 | Malformed config can send | `highways/config.py` `read`: if anything in a parseable file is malformed — `default` not exactly `"on"`/`"off"`, `repos` present and not a dict, any key not a string, any value not exactly `"on"`/`"off"` — the whole file counts as `{"default": "off", "repos": {}}`. Fail closed: no partial reading. Tests for each case, each ending `not-enabled` with zero requests | `highways/config.py`, `test/test_search.py` | Terra (gpt-5.6-terra), xhigh, fresh lane |
| N2 | Test-set file labels | `highways/evalset.py` `_named_at_tree`: the same token rule as `search.named_files` (backticked token whole; link target drops a trailing `"title"` and `#anchor`); test that `eval written` records `my file.py` and `name#1.py` | `highways/evalset.py`, `test/test_eval_written.py` | same lane |
