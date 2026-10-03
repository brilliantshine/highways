# highways — router creation, upkeep and search for any git repository

If `highways` is installed, run `highways search "<what you're looking for>"` before reading code to find where something lives.

Highways owns router documents (`AGENTS.md`/`CLAUDE.md`, a directory's short note on what it
owns, what must never happen there, and where to go next) in any git repository. It creates
them with a person's confirmation, keeps them true as code changes without asking, and
searches them to narrow a question to a few directories. It works without wheelchair; wheelchair
uses it when `highways` is on `PATH`.

The organizing idea: **a router that lies is worse than no router.** Everything that writes one
leaves it true or leaves it alone, and search only ever says where to start reading, never what
the code does.

## Flow

```
search:  question -> sending switch, key, routers? -> one parallel round to Jev (reach, own)
         -> walk the router tree in plain code -> ranked directories -> optional file step
upkeep:  per-message hook snapshots the repo -> agent works -> end-of-turn hook runs sweep
         -> agent sent back once to fix the routers its change made false
create:  scan.sh -> classify directories -> pre-write list -> person confirms -> write
```

## Layout

| Directory | Owns |
|---|---|
| `bin/` | `highways`, the one entry point; symlinked onto `PATH` by `install.sh`, so it finds the repo through its real path |
| `highways/` | the Python package behind every subcommand: search, router discovery, the Decisions client, the sending switch, snapshot, sweep, hooks, and the test-set tools |
| `create/` | `scan.sh`, moved from wheelchair, unchanged except that its git calls pass `--no-optional-locks`; read-only, writes nothing anywhere |
| `hooks/` | the per-message and end-of-turn hooks, thin shell entry points into `highways/hooks.py` |
| `protocol/` | what an agent reads to do each job: `create.md`, `routers.md` (the format), `sweep.md`, `search.md` |
| `search/` | `bars.json`, the confidence bars, set only by a passing test-set run |
| `skills/`, `codex/` | the `/highways` wrappers for Claude Code and Codex; one pointer each, no content |
| `test/` | the offline suites; no network, fixtures built in temp directories |
| `docs/plans/` | plan records; not read at run time |

## Files that carry a constraint

| File | Constraint |
|---|---|
| `highways/decisions.py` | every request carries `provider: {"zdr": true}`; there is no path that sends without it |
| `highways/config.py` | the sending switch lives outside every repo; nothing inside a repo can turn sending on |
| `highways/cli.py` | `enable` and `default on` refuse without a terminal and a typed confirmation |
| `highways/hooks.py` | every hook path exits 0 silently on failure, and hooks skip headless lanes and subagents |
| `highways/evalset.py` | works only in fresh temp clones; writes only under `~/.cache/highways/eval/`, and `search/bars.json` only after the live run passes every gate |
| `highways/eval_review.py` | the review page binds 127.0.0.1 only and refuses any request without its random token |
| `install.sh` | rewrites its own hook groups in place and leaves every other entry untouched |

## Boundaries

- Never send anything to a model except through OpenRouter with zero data retention required,
  because the team's data rules allow nothing else.
- Never read code or directory listings during search, because highways is not an index; routers
  are what people keep true.
- Never write inside a target repository or its `.git` from search, the hooks or sweep, because
  they run in repositories highways doesn't own.
- Never commit a test-only or example router anywhere, because both harnesses load routers as
  live instructions.
- Never create a router without a person's confirmation, and never reformat an existing one.
- Never run a git command without `--no-optional-locks`, because even a status refresh can write
  `.git/index`.

## Navigation order

`highways search` → the routers it names → grep → graphify last.

## graphify

Routers are the spine; graphify is an opt-in supplement. It never answers "where does X live" or
"what owns Y". A stale graph misroutes silently instead of failing, so check its freshness before
trusting it. It earns its place only on blast radius, distance between far-apart concepts, and
community structure, and every result is confirmed in source. The graph is per-clone:
`graphify-out/` is gitignored here, so it cannot carry a contract.

## Verification

```
bash create/test/run.sh
python3 -m unittest discover -s test
bash test/hooks.sh
bash test/install.sh
```

The test set (`highways eval draft | written | review | score | latency`) needs `OPENROUTER_API_KEY`, sends data,
and is run by hand, never in CI.
