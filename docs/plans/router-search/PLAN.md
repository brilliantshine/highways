---
slug: router-search
status: approved   # planning | ready-for-review | approved | implementing | verifying | done
created: 2026-10-02
---

# Highways: router creation, upkeep and fast search

**Idea:** `IDEA.md` — what this is for and why, in plain language. Read it first; it is
the north star this plan serves. Goal and Constraints live there, not here, so they don't
get buried as this file grows.

## Open Questions

Ordered by leverage; discussed one at a time. A settled question moves to the Decision
Log and is deleted from here.

## Watch List

Things noticed that need looking into — not yet decisions for the user. Written down the
moment they're spotted so they can't be forgotten, surfaced to the user one line at a
time as they appear, and emptied before Stage 1 exits.

Each item ends up settled by the agent (noted in the Log), promoted to an Open Question,
promoted to a Constraint or Accepted Risk, or waved off by the user.

| # | Noticed | What needs looking into | Raised to user? | Outcome |
|---|---------|-------------------------|-----------------|---------|
| W1 | 2026-10-02 | Jev is unverified: access, real API shape, latency, and whether its probabilities compare across separate calls. Since D28: whether OpenRouter passes Jev's typed answers and their probabilities through. Partly checked 2026-10-02 from OpenRouter's docs: a dedicated Decisions API (not chat) returns a probability per yes/no question (D31). Still unchecked: whether that alpha endpoint honours the `zdr` provider preference, real latency, and whether probabilities compare across separate requests | yes | Settled by the agent: D34 makes the ZDR check the first task, and it fails closed. Latency and whether probabilities compare across requests are measured by the test set (D27) and recorded as an Accepted Risk |
| W2 | 2026-10-02 | Whether Codex CLI has an end-of-turn hook like Claude Code's `Stop`; Q4's recommendation depends on it. Partly checked 2026-10-02: Codex 0.159.3 accepts a `Stop` entry in `~/.codex/hooks.json` (one is registered there). Not checked: whether a Codex `Stop` hook can send the agent back to work the way Claude Code's can | yes | Settled by the agent, 2026-10-02: Codex Stop hooks support `{"decision": "block", "reason"}` and `stop_hook_active` (codex.danielvaughan.com hooks guide; Codex commit "[hooks] stop continuation & stop_hook_active mechanics", #14532). D32. Re-confirmed live by the hook tests on the installed Codex |
| W3 | 2026-10-02 | How many repos on this machine carry routers, for the test set (MAP.md "Not checked") | yes | Checked 2026-10-02 (every git repo under `~` to depth 7): two codebases, wheelchair (6 routers) and work repo (about 40, 13 checkouts). Became Q6 |
| W4 | 2026-10-02 | Wheelchair files that reference the router pieces and need repointing at removal: `AGENTS.md`, `README.md`, `CONTRIBUTING.md`, `protocol/{AGENTS,implementation,graphs,sensitivity,spine,routers}.md`, `skills/AGENTS.md`, `skills/spine/`, `codex/prompts/spine.md`, `spine/`, `viewer/test/server.test.js` | yes | Settled by the agent: the Spec's "Removal from wheelchair" lists each file and what happens to it. `viewer/test/server.test.js` only uses `protocol/routers.md` as sample prose and needs no change |
| W5 | 2026-10-02 | How the end-of-turn hook knows what this turn changed: the working tree against a snapshot the per-message hook takes at the start of the turn, or plain `git status`, which also shows changes from before the turn | yes | Settled by the agent: D33 |
| W6 | 2026-10-02 | The work repo's routers differ from wheelchair's format: the root is a "kind of work → document to read" table, routers are cumulative instructions, some are 5 to 7 lines, and each `CLAUDE.md` is a symlink to `AGENTS.md`. The own question (D22) relies on a router saying which subdirectories it covers; some here may not | yes | Settled by the agent: search reads router text as prose and never assumes the wheelchair format (wheelchair `protocol/routers.md:128-135` already says an existing router is never measured against it). D27 puts this style in the test set on purpose, so the bars are tuned across both styles |

## Decision Log

Append-only. A reversal is a new entry superseding the old, never an edit.

| # | Decision | Rationale | Source |
|---|----------|-----------|--------|
| D1 | Highways keeps routers true automatically as code changes, taking over wheelchair's upkeep; once highways does creation and upkeep, they are removed from wheelchair | Collin's amendment to the draft idea | idea-change |
| D2 | Creating routers still needs a person's confirmation; updating an existing router a change made false does not | Automatic upkeep can't wait on confirmation, and wheelchair's upkeep already edits without asking | idea-change |
| D3 | The search is a command-line program. An MCP server can wrap it later | Both harnesses run shell commands; every wheelchair executable is already a script | defaulted |
| D4 | The model sits behind one interface with Jev as the first backend. With no backend available, search reports "unavailable" and the agent greps | IDEA.md forbids depending on unconfirmed Jev details; grep is the stated fallback | defaulted |
| D5 | Search returns ranked directories, each with its probability and router path, plus an explicit "not confident, grep instead" verdict when the top result is below a threshold. The threshold is set from the test set, not guessed | IDEA.md "never sends an agent confidently to the wrong place" | defaulted |
| D6 | Search reads routers only: no file listings and no code. In a repo with no routers it says so and names the create command | IDEA.md "Not doing": no index of every file or symbol | defaulted |
| D7 | The scanner (`spine/scan.sh` and its tests), the router format and the creation sequence move to highways unchanged in behaviour; only paths change | They are self-contained (MAP.md) and already guarded | defaulted |
| D8 | Wheelchair detects highways by its presence on `PATH`, the rule wheelchair `protocol/lanes.md` already uses for harnesses | Neither tool may require the other; reuse the existing presence rule | defaulted |
| D9 | Removal from wheelchair is this plan's last phase, done only once highways' creation, upkeep and search tests pass with wheelchair absent | IDEA.md "Not doing" and D1 | defaulted |
| D10 | New highways code is Python 3.11+ (already required by wheelchair's `seen/set.sh`); the moved scanner stays bash | No new runtime dependency | defaulted |
| D11 | Agents reach the search two ways: a command the agent runs (prompted by a root-router line and by wheelchair's stages), and an automatic per-message hook that runs the same command on the person's message and speaks only when confident | The hook covers the start of a task without relying on obedience; the command covers mid-task questions and is what wheelchair calls | user |
| D12 | The hook is a `UserPromptSubmit` hook on both harnesses, with a short timeout. It exits silently on every failure, on a non-confident result, outside a repo with routers, and in headless lanes and subagents (the `WHEELCHAIR_LANE` / `agent_id` rule wheelchair's `seen/hook.sh` uses) | A turn the hook delays or blocks is a failure noticed every time; wheelchair's seen hook already proves this shape works on both harnesses (wheelchair `protocol/seen.md`) | defaulted |
| D13 | Sending messages and router text to an outside model is off by default, switched on per repo. A user-level setting flips the default to on, after which a repo can still be switched off | Collin: off by default, with a setting to default on. Nothing leaves the machine for a repo nobody enabled | user |
| D14 | The default setting and every per-repo switch live in one user-level config file outside any repo, keyed by the repo's absolute path. Nothing inside a repo can switch sending on | A repo's own files are attacker-controlled in a clone; a committed switch could make a stranger's repo send your messages out. Same reason wheelchair's seen hook reads nothing inside a repo (wheelchair `protocol/seen.md`) | defaulted |
| D15 | A search asks every router in parallel, separately: "does this directory own X?", and ranks directories by the probability of each answer | Speed doesn't depend on repo depth, and one wrong answer can't hide the right directory. Revisit if Watch W1 finds Jev's probabilities don't compare across calls | user |
| D16 | When the top directory clears a second, higher bar, search asks about each file that directory's router names, drops any that no longer exist, and returns the rest ranked under that directory. Files a router doesn't name are never considered | Collin chose it; it stays inside IDEA.md's "no index of every file" and D6 (routers only) | user |
| D17 | Both bars (directory and file) are set from the test set (Q6), not guessed; the file bar is never lower than the directory bar | Same reasoning as D5 | defaulted |
| D18 | Outside wheelchair, upkeep runs when an agent finishes its turn: an end-of-turn hook checks whether the turn's changes touched a directory with a router and, if so, sends the agent back to check and fix those routers before it finishes. On a harness whose end-of-turn hook can't send the agent back (Watch W2), it warns instead | Fixes happen automatically, at the moment of the change, by the agent that made it | user |
| D19 | Supersedes D16's "the top directory": every directory clearing the file bar gets the file step, not only the top one. The rest of D16 stands | Collin: any router above the threshold gets the second step | user |
| D20 | Search returns every directory that clears the directory bar, ranked, capped at 5; each one that clears the file bar carries its own ranked files | Several right answers are normal (a change spanning two directories); a cap keeps the answer short. The cap is tuned with the bars (D17) | defaulted |
| D21 | The end-of-turn hook follows D12's rules too: silent on failure, and skipped in headless lanes and subagents. Inside a wheelchair run, the lead's sweep after each lane runs highways' sweep instead | One owner per moment: wheelchair's lead already sweeps after lanes (wheelchair `protocol/implementation.md:218-223`) | defaulted |
| D22 | Supersedes D15. Search scores every router in one parallel round with two yes/no questions: "is X anywhere in this directory, subdirectories included?" (reach) and "is X in this directory's own files, or a subdirectory it lists as having no router of its own?" (own). Plain code then walks the router tree top-down over those scores with no further model calls: it enters a directory whose reach score clears the walk bar, and a directory it reaches whose own score clears the answer bar is an answer | Collin's top-down shape with one round of waiting; the own question lets the root be an answer only when X really sits in it (wheelchair's `viewer/` case) | user |
| D23 | The walk also enters a directory whose reach score misses the walk bar when some router inside it has an own score above the answer bar | Every score is already in hand, so one weak parent can't hide a strong answer | defaulted |
| D24 | Three bars (walk, answer, file) all come from the test set; answer ≤ file. Extends D17 | Same reasoning as D5 | defaulted |
| D25 | The agent decides whether a touched router is still true: it reads each router in a directory its turn changed, against its own change, and fixes what's false. No model screens it, and no code leaves the machine for upkeep | Routers are short and only touched ones are read; a model screen would send code out and fail silently, the failure IDEA.md calls worse than no router | user |
| D26 | Test questions come from git history: a commit whose changes sit in one or a few routed directories gives a question (its message) and the right answers (those directories, and any router-named files it touched). Commits touching only routers or more than 5 directories are skipped | Real questions with known answers, no hand-writing, and the same generator works on any repo | defaulted |
| D27 | The test set is wheelchair and the work repo | Collin; only the work repo has routers deep and many enough to test the walk. Its routers are in a different style from wheelchair's (Watch W6), which the test should cover anyway | user |
| D28 | Every model call goes to Jev through OpenRouter with zero data retention required on the request, never to TypeSafe AI directly. Added to IDEA.md Constraints | Collin: the team already serves Jev requests this way; TypeSafe AI directly isn't considered safe | user |
| D29 | Tests on the work repo run on a fresh `git clone` into a temp directory, never in an existing checkout and never through `git worktree` (which writes into the source repo's `.git`). Nothing in the test suite writes to the source checkout | Collin: make a copy so nothing changes unnecessarily | user |
| D30 | One command, `/highways`, with subcommands `create`, `search` and `sweep`, on both harnesses. Highways never ships a `/spine` | One name per tool; two `/spine` commands installed during the overlap would clash | user |
| D31 | Each router is one request to OpenRouter's Decisions API (`POST https://openrouter.ai/api/alpha/decisions`, model `typesafe/jev-1.13`): `state` holds the router's directory path and full text plus the question, and `questions` holds two `noul` (yes/no) questions, `reach` and `own`, each answered with the probability of yes. All routers' requests go out in parallel | OpenRouter's Jev docs: questions about the same state belong in one request, each `noul` answer is a probability, and the window is 32,000 tokens (routers run 5 to 133 lines). Checked 2026-10-02 at openrouter.ai/docs/guides/community/jev and jev-tutorial | defaulted |
| D32 | On both harnesses the end-of-turn hook is a `Stop` hook that sends the agent back with `{"decision": "block", "reason": ...}`, at most once per turn: it does nothing when its input carries `stop_hook_active: true` | Codex's Stop hook supports the same continuation shape as Claude Code's, including `stop_hook_active` (Watch W2). Once per turn rules out a loop | defaulted |
| D33 | "What this turn changed" comes from a snapshot the per-message hook takes at the start of each turn, kept outside the repo: `HEAD`, plus a content hash of every path `git status` reports. At the end of the turn, a path counts as changed if it is in a commit made since that `HEAD`, or is dirty now with a hash that differs from the snapshot's or that wasn't in it. With no snapshot, every path `git status` reports counts | Plain `git status` blames this turn for older edits; nothing may be written into the repo or its `.git` to take the snapshot. Over-reporting only means checking an extra router (Watch W5) | defaulted |
| D34 | Before anything else is built, a live check against OpenRouter's Decisions API must pass: a request carrying `provider: {"zdr": true}` is accepted and answered. If the endpoint refuses or ignores ZDR, highways never sends, and the plan goes back to planning. Highways never sends a request without `zdr: true` | D28 makes ZDR a hard limit, and OpenRouter's docs don't say the alpha Decisions endpoint honours it (Watch W1) | defaulted |
| D35 | The OpenRouter key comes from the `OPENROUTER_API_KEY` environment variable only. No key means search answers "unavailable" | The same variable OpenRouter's own tools use; highways stores no secret | defaulted |
| D36 | Request round budget 1 s, file step 0.5 s; the test set gates on 95th-percentile latency ≤ 1 s | IDEA.md "well under a second"; both reviewers found 3 s + 2 s budgets with no gate | review-round-1 |
| D37 | The test set is drafted from filtered, sampled history (up to 100 commits per repo), reviewed by a person, scored once with probabilities cached and bars swept offline, pooled across repos, and gated on answered rate, top-wrong, answer precision, file precision, narrowing and latency. All of it lives outside any repo | Round 1: commit subjects were mostly bookkeeping, the metric let wrong extras through, there was no minimum usefulness bar, no pooling, and no cost limit | review-round-1 |
| D38 | `highways enable` and `default on` need a terminal and a typed confirmation; the `not-enabled` answer tells the agent only the person can turn sending on | Round 1: the answer invited the agent, or a cloned repo's router, to switch sending on itself | review-round-1 |
| D39 | A changed path also maps to every ancestor router that names it, not only the nearest router | Round 1: wheelchair's root router names `seen/wording.sh` (`AGENTS.md:55`), so it goes false when that file moves | review-round-1 |
| D40 | Every git command passes `--no-optional-locks`; the session sweep also counts snapshot paths that are no longer dirty; diffs use `--no-renames` | Round 1: `git status` can write `.git/index`; deleted untracked files went unseen; `--name-only` drops a rename's old path | review-round-1 |
| D41 | The moved docs drop every wheelchair-only reference; the navigation order becomes `highways search → routers → grep → graphify`; the search line is a second permitted addition to an existing root router, proposed by every `create` run that finds it missing | Round 1: dangling references, and the line would never reach repos that already have routers | review-round-1 |
| D42 | Wheelchair's implementation briefs carry the search line | IDEA.md names implementing among the stages that use highways; round 1 found only planning did | review-round-1 |
| D43 | Phase 0 passes only when the per-request ZDR call succeeds, the ZDR endpoint list includes Jev, and Collin confirms account-level ZDR-only | Round 1: a response can't prove ZDR was applied | review-round-1 |
| D44 | Supersedes D23. The walk enters a child only when its `reach` clears the walk bar, so an answer needs a "yes, somewhere in here" from every router above it. The test set scores this walk against a flat `own`-only ranking from the same cache and keeps the walk only if it lowers top-wrong; otherwise `bars.json` sets `mode: flat` | Collin, on review round 1's finding that D23 made the walk do nothing. The walk then adds a second opinion against confident wrong answers | user |
| D45 | Round-2 clarifications: the root is always entered; budgets 0.7 s + 0.3 s, so a whole search stays within 1 s; latency, narrowing and walk-versus-flat are measured as the Spec now states; the answer and file bars never go below 0.5; the session sweep reads commits one by one; with highways absent, wheelchair skips all four router steps; the root-router line is conditional on highways being installed; the scope of the creation check and the covered-repo edge case are amended | Each closes a round-2 finding where a worker would have had to stop and ask | review-round-2 |
| D46 | Supersedes D44's rule for choosing between walk and flat, which D45 replaced without saying so: keep `walk` only if its best answered rate under the same limits beats `flat`'s. Also: latency is measured by a separate live run of the real search after bars are chosen, and scoring runs without budgets; narrowing is the union of a question's answers, over answered questions only, falling back to own files when a file step returns nothing; bar sweep ranges are stated; the session sweep includes merges; the covered-repo prose, `spine.md:9`, wheelchair's post-PASS sweep and COMPLETION template are covered | Review round 3 | review-round-3 |
| D47 | A fourth review round, limited to round 3's fixes; the review cap resets | Collin, after round 3 ended unclean on precision findings only | user |
| D48 | The latency run enables its temp clone through a temporary `HIGHWAYS_CONFIG` and also recomputes answered rate, top-wrong and narrowing from the real search's output; the gate applies to both the cached and the live results; narrowing joins the bar-selection limits; the wheelchair-only "live case" passage in the format doc is dropped | Review round 4 | review-round-4 |
| D49 | The live run checks every metric and gate, answer and file precision included; phase 5 runs `eval latency` and commits `bars.json` only after it passes; the three `eval` subcommands are listed with their arguments; the citation for the dropped format passage is corrected | Review round 5 | review-round-5 |
| D50 | Question files record their source path and HEAD; `score` and `latency` each make fresh temp clones from it; `score` writes candidate bars outside the repo, and only a passing live run copies them into `search/bars.json` | Review round 6 minors | review-round-6 |
| D51 | The file step is optional. Its bar is the lowest setting with file precision ≥ 80% and at least one file returned. If none qualifies, `file` is `null` and search ships naming directories only; the file-precision gate applies only while the step is on | Collin, on review round 6's finding that nothing picked the file bar | user |

## Spec

The settled design, grown as decisions land. Bar: a fresh agent with no conversation
history can implement from this section alone — behavior, boundaries, edge cases,
non-goals, and concrete validation commands.

A Mermaid diagram of the flow belongs here, added by Stage 2 at approval — not while the
Spec is still churning. See `protocol/diagrams.md`.

### The three flows at a glance

Drawn at approval from `graphs/q1-reach.json`, `graphs/search-flow.json` and
`graphs/q4-upkeep-trigger.json`, showing only the options that were decided. The prose below
is the authority. Each picture repeats what it says.

How an agent comes to ask: the per-message hook runs search on the person's message and
speaks only when confident; the agent runs the same command whenever it needs to find
something, prompted by the root-router line and wheelchair's stages.

```mermaid
flowchart TD
  M[person sends a message] --> H[per-message hook searches it]
  H --> C1{confident answers?}
  C1 -- yes --> HINT[agent starts with the likely places in hand]
  C1 -- no, or any failure --> QUIET[hook says nothing]
  HINT --> W[agent works]
  QUIET --> W
  L[root-router line or wheelchair step says search first] --> R[agent runs highways search]
  W -- needs to find something --> R
  R --> S[search, below]
```

One search: every router is asked two yes/no questions in one parallel round, plain code walks
the router tree over the answers, and confident answers may get a file step.

```mermaid
flowchart TD
  Q[question] --> SW{sending on for this repo, key set, routers present?}
  SW -- no --> NO[not-enabled, unavailable or no-routers; nothing sent]
  SW -- yes --> ASK[ask every router at once: anywhere in here? in your own files?]
  ASK --> WALK[walk from the root: go into a child only if it said anywhere in here]
  WALK --> ANS{any directory reached says own files, above the answer bar?}
  ANS -- no --> NC[not confident, grep instead]
  ANS -- yes --> TOP[keep the best five]
  subgraph files [Narrow to files, when the file step is on]
    FB{above the file bar?} -- yes --> FASK[ask about each file its router names, drop missing files]
  end
  TOP --> FB
  FB -- no --> OUT[ranked directories]
  FASK --> OUT2[ranked directories with likely files]
```

Upkeep outside wheelchair: as the agent tries to finish, the end-of-turn hook checks what this
turn changed and sends the agent back, once, to check the routers covering it.

```mermaid
flowchart TD
  E[agent changed code this turn] --> STOP[agent tries to finish]
  STOP --> T{did the turn touch anything a router covers or names?}
  T -- no --> DONE[turn ends]
  T -- yes, first time this turn --> BACK[agent is sent back: read those routers against the change, fix what is false]
  BACK --> STOP2[agent finishes; the hook does not send it back twice]
```

### Scope

Highways is a standalone repo (`~/projects/personal/highways`) that owns three jobs for any
git repository:

- **create**: proposing new routers and writing them only after a person confirms (D2, D7);
- **sweep**: keeping existing routers true as code changes, without asking (D1, D2, D18, D25);
- **search**: narrowing a question to a few directories, and sometimes files, from the
  routers alone (D6, D15–D24).

A router is a directory's `AGENTS.md`/`CLAUDE.md`. It works with wheelchair absent, and
wheelchair uses it when it is on `PATH` (D8). Wheelchair's copies of the router pieces are
removed in the last phase (D9).

Non-goals, binding on every phase: no index of files or symbols, and search never reads code
or directory listings (D6, D16). Nothing replaces grep or reading code. No router is created
without confirmation. Nothing is sent to any model except through OpenRouter with `zdr: true`
(D28, D34). Nothing reformats an existing router or measures it against the format (wheelchair
`protocol/spine.md`, "Editing existing content"). Nothing example-like is committed as a
router anywhere, since both harnesses load them as live instructions (IDEA.md Constraints).

### Layout of the highways repo

```
bin/highways              entry point (Python 3.11+, D10); every subcommand below
highways/                 the Python package: search, walk, config, snapshot, OpenRouter client
create/scan.sh            moved unchanged from wheelchair spine/scan.sh (D7)
create/test/run.sh        moved unchanged from wheelchair spine/test/run.sh, paths adjusted
protocol/routers.md       moved from wheelchair protocol/routers.md (the format)
protocol/create.md        moved from wheelchair protocol/spine.md; "/spine" becomes "/highways create"
protocol/sweep.md         the upkeep rule (below)
protocol/search.md        how an agent uses search results
hooks/prompt.sh           the per-message hook (D11, D12, D33)
hooks/stop.sh             the end-of-turn hook (D18, D21, D32)
skills/highways/SKILL.md  Claude Code wrapper, one pointer per subcommand, no content
codex/prompts/highways.md Codex wrapper, same convention
install.sh                renders wrappers, installs bin/highways onto PATH, writes hook entries
search/bars.json          the three bars and the cap, as set by the test set (D24)
test/                     fixture suites (below), no network
eval/                     the test-set runner (needs a key, run by hand)
AGENTS.md                 highways' own root router, written through `highways create` itself
```

Wrappers follow wheelchair's convention (wheelchair `AGENTS.md`, "A wrapper carries no
content"): a placeholder `{{HIGHWAYS_ROOT}}` that `install.sh` renders to the absolute clone
path, and one line pointing at a `protocol/` file.

### Commands (D30)

Slash command on both harnesses: `/highways create <path>`, `/highways search <question>`,
`/highways sweep`. Each points at the matching `protocol/` file. Highways never installs a
`/spine`.

Shell commands, used by agents, hooks and wheelchair:

| Command | Does |
|---|---|
| `highways search "<question>" [--repo PATH] [--json]` | the search below. `--repo` defaults to the git toplevel of the working directory |
| `highways scan <path>` | runs `create/scan.sh` (read-only JSON, unchanged contract) |
| `highways sweep [--base REV] [--session ID]` | lists the routers covering what changed (below); writes nothing |
| `highways enable [PATH]` / `highways disable [PATH]` | sets the repo's sending switch (D13, D14) |
| `highways default on\|off` | sets the user-level default (D13) |
| `highways eval draft --source PATH` | drafts test questions from a fresh temp clone (below) |
| `highways eval score --questions FILE [--questions FILE ...]` | scores reviewed questions once, caches them, and chooses the bars (below) |
| `highways eval latency --questions FILE [--questions FILE ...]` | runs the real search on reviewed questions in fresh temp clones and checks the gate live (below) |

Exit codes: 0 for every search result, including "not confident" and "unavailable", which are
answers rather than failures; 1 for a refusal the caller must act on (outside a git repo); 2
for misuse.

### Search

Steps, in order:

1. **Find the repo and its routers.** Router discovery reuses `create/scan.sh`'s walk rules:
   skip git-ignored, dotted and nested-repo directories, and resolve symlinks so an
   `AGENTS.md`/`CLAUDE.md` pair counts as one router. A directory holding two real router files
   sends both texts, each labelled with its filename. A router's parent is the nearest
   ancestor directory that has one. No routers at all: answer `no-routers`, naming
   `/highways create`. Send nothing.
2. **Check the switch.** Read `~/.config/highways/config.json` (D14):
   `{"default": "off", "repos": {"<abs repo path>": "on"|"off"}}`. A missing or unparseable file
   counts as `{"default": "off"}`. If sending is off for this repo, answer `not-enabled`
   with the note "sending is off for this repo; only the person can turn it on, from their own
   terminal", and send nothing. Nothing inside the repo is read for this. `highways enable`
   and `highways default on` refuse unless stdin and stdout are both a terminal, and then
   ask the person to type the repo's directory name (for `default on`, the word `on`) before
   writing. `disable` and `default off` need no confirmation, since they only stop sending
   (D38).
3. **Check the key.** If `OPENROUTER_API_KEY` is empty, answer `unavailable` (D35).
4. **One round of requests (D22, D31).** For every router, in parallel, one
   `POST https://openrouter.ai/api/alpha/decisions` request with:
   - `model: "typesafe/jev-1.13"` and `provider: {"zdr": true}` (D28, D34);
   - `state` holding `directory`, `router` (the full text) and `question`;
   - two `noul` questions:
     - `reach`: "Is what the question asks about anywhere in this directory, its
       subdirectories included?"
     - `own`: "Is it in this directory's own files, or in a subdirectory this router names
       as having no router of its own? A subdirectory with its own router does not count."

     Each question carries `criteria` for `true` and `false` written to the same
     wording.

   The whole round has a 0.7-second budget (D36, D45). If any request fails, times out, or comes back
   without both probabilities, the search answers `unavailable` and none of the round is
   used.
5. **Walk in plain code (D22, D44).** Start at the root router. Without one, start from a
   virtual root whose children are the topmost routers. The root is always entered, whatever its own `reach`. Below it, enter a
   child only if its `reach` is at least the walk bar; there is no other way in. So an answer
   counts only if every router between it and the root, itself included, said "yes, somewhere
   in here" (D45). Every router reached whose `own` is at least
   the answer bar is an answer. The root is reached on every search and is an answer only
   through its own `own` score. When `search/bars.json` has `"mode": "flat"`, the walk is
   skipped and every router whose `own` clears the answer bar is an answer.
6. **Rank and cap (D20).** Sort answers by `own` descending, then by path, and keep the first
   5. None: answer `not-confident`.
7. **File step (D16, D19, D51).** Skipped entirely when `bars.json` has `"file": null`.
   Otherwise, for each kept answer whose `own` is at least the file bar:
   - collect the files its router names: every backticked token or markdown link target that
     resolves, against the router's directory or else the repo root, to an existing regular
     file inside the repo; anything else is dropped;
   - if any are left, send one more request (same model, same `zdr`) with the router text and
     question as `state`, and one `noul` question per file: "Is what the question asks
     about in this file?";
   - keep files at or above the answer bar, ranked, at most 5 per answer.

   These requests go out in parallel with a 0.3-second budget, so a whole search stays within 1 second (D36, D45). A failure here drops only the
   files for that answer; the directory answer stands.
8. **Answer.** Text: one line per answer giving the directory, its router path and
   probability, then its files indented under it. Then one line saying the answers are where
   to start reading, not a guarantee. `--json`:
   `{"status": "answers"|"not-confident"|"not-enabled"|"unavailable"|"no-routers",
     "answers": [{"dir", "router", "own", "reach", "files": [{"path", "p"}]}], "note"}`.

The bars, the cap and the mode live in `search/bars.json` (`walk`, `answer`, `file`, `cap`,
`mode`). They hold 0.5, 0.7, 0.85, 5 and `walk` until the test set sets them, and must always satisfy
`0.5 ≤ answer ≤ file` whenever `file` is not `null` (D17, D24, D45, D51).

### The test set (D26, D27, D29, D37)

Three steps. Every file the test set produces lives under `~/.cache/highways/eval/`, never in
any repo, because questions drawn from a work repo are that repo's content.

1. **Draft.** `highways eval draft --source PATH` makes a fresh `git clone` of `PATH` into a
   temp directory. It never uses `git worktree`, and never touches the source checkout. It
   samples up to 100 commits with a fixed seed. A commit qualifies when:
   - it is not a merge;
   - it changes at least one file that isn't markdown, and not only files under `docs/`;
   - it touches no router file;
   - at its parent commit, its changed files sit under 1 to 5 routed directories.

   Each qualifying commit gives a draft question (its subject line, with any
   `type(scope):` prefix and leading ticket id such as `ABC-123:` stripped). Its answers
   are the directories each changed file maps to (the router covering it at the parent), plus
   any router-named files it touched. The draft is written as
   `~/.cache/highways/eval/<repo>-questions.jsonl`, headed by `{"reviewed": false, "source": "<absolute source path>", "head": "<source HEAD when drafted>"}`.
   `score` and `latency` each make their own fresh temp clone from that `source` (D50).
2. **Review.** A person edits the file:
   - rewrites a question into "where is the code that ..." form where the subject isn't one;
   - deletes questions that can't be fixed;
   - sets `"reviewed": true`.

   `score` refuses a file still marked `false`.
3. **Score.** `highways eval score --questions FILE [--questions FILE ...]` checks out each
   question's parent commit in that repo's temp clone and runs one live round per question
   (the enable switch is bypassed for the temp clone only). Scoring runs with no time budgets (a
   10-second timeout per request), so the cache is complete. A question whose request still
   fails is dropped and counted in the report. The file step runs for every directory with
   `own` at or above 0.5, which is why the sweep never tries an answer or file bar below 0.5
   (D45). The sweep steps every bar by 0.05: answer and file from 0.5 to 0.95, walk from
   0.1 to 0.95 (`reach` is cached for every router) (D46). Every probability is cached under `~/.cache/highways/eval/scores/`. Every bar setting is then swept
   offline over the cache; no setting sends another request. All question files are pooled
   into one result, and the chosen bars are written to `~/.cache/highways/eval/bars.candidate.json` with the date and
   the source commits measured.

Metrics, over the pooled questions:
- answered rate: questions with at least one answer;
- top-wrong rate: answered questions whose first answer is wrong;
- answer precision: right answers ÷ all answers returned, so wrong extras count against it;
- recall: questions with a right directory among the answers;
- file precision and file recall: against the router-named files each commit touched;
- narrowing, per answered question: the share of the repo's tracked files its answers point
  at, as a union. An answer points at its returned files if its file step returned at least
  one. Otherwise it points at the directory's own files: those under it, minus subdirectories
  that have their own router. Unanswered questions don't enter the median, since the answered
  rate already counts them (D45, D46);
- latency and live results: measured separately, after the bars and mode are chosen.
  `highways eval latency` runs the real `highways search` (production budgets, the candidate bars,
  mode and cap) once per reviewed question at its parent commit. It runs with
  `HIGHWAYS_CONFIG` pointed at a temporary config that enables only the temp clone, and never
  touches the person's own config. Each search is timed from command start to printed answer,
  and the median and 95th percentile are reported. It makes its own fresh temp clones. The same run
  recomputes every metric above from what the real search printed, counting an
  `unavailable` answer as unanswered (D46, D48, D49). Only when every gate passes does it copy
  the candidate bars into `search/bars.json`. Until then the working tree's file keeps its
  previous values (D50).

For each mode separately, the walk and answer bars are chosen to maximise the answered rate
subject to top-wrong ≤ 5%, answer precision ≥ 80% and median narrowing ≤ 10% (D48). Then the
file bar is chosen as the lowest setting whose file precision is ≥ 80% with at least one file
returned. That is the setting that names files most often while staying accurate. If no
setting qualifies, `bars.json` sets `"file": null`, the file step is off, and search ships
naming directories only (D51). Both modes are
scored from the same cache. `walk` is kept only if its best answered rate is higher than
`flat`'s. Under the same limit on wrong answers, a walk that filters out wrong answers shows up
as answering more often. A tie goes to `flat`, the simpler mode (D44, D45). The plan goes back to planning,
rather than shipping, if any of these fail. They are checked twice: on the cache with the
best bars, and again on the live latency run, so a search that times out in real use can't
pass on cached scores (D48, D49):
- answered rate ≥ 50%;
- top-wrong ≤ 5%;
- answer precision ≥ 80%;
- file precision ≥ 80%, only while the file step is on; with it on, the live run must also
  return at least one file, or the step is switched off rather than shipped empty (D51);
- median narrowing ≤ 10%;
- 95th-percentile latency ≤ 1 second (live run only).

Not part of CI: it needs a key and sends data. With 100 questions per repo and about 40
routers, a full run is a few million input tokens, well under a dollar at the listed price.

### The per-message hook (D11, D12, D33)

`hooks/prompt.sh <harness>` is a `UserPromptSubmit` hook on both harnesses with a 2-second
harness timeout. In order:

1. Exit 0 silently if `WHEELCHAIR_LANE` or `HIGHWAYS_LANE` is non-empty, or the input carries
   `agent_id` (a headless lane or a subagent; wheelchair `protocol/seen.md`, "The hook").
2. Find the git toplevel from the input's `cwd`. If there is none, exit 0 silently.
3. Take the snapshot (D33): `HEAD` plus a sha256 of each path that
   `git --no-optional-locks status --porcelain=v1 -z -uall` reports. Every git command
   highways runs passes `--no-optional-locks`, so even an index refresh is never written
   (D40). It goes to
   `~/.cache/highways/sessions/<session_id>.json`, overwritten every message. It is taken even
   when sending is off, because it is local. Nothing is written in the repo or its `.git`.
4. If the prompt has fewer than 4 words, stop here. Otherwise run the search with a
   1.5-second overall budget. Only on `answers` it prints the text answer as added context,
   headed "highways: likely places for this request (start here, confirm by reading)". Every
   other status, error or timeout prints nothing.

Every path exits 0, so the turn always proceeds.

### Upkeep: the end-of-turn hook and `sweep` (D18, D21, D25, D32, D33)

`highways sweep` works out the changed paths (D33, D40):
- with `--session ID`, against that session's snapshot:
  - every path touched by any commit made since the snapshot,
    `git log --no-renames --diff-merges=first-parent --name-only -z --format= <snapshot HEAD>..HEAD`
    (a merge's own changes would otherwise be left out). Per commit,
    not an end-to-end diff, so a change that a later commit undoes is still caught (D45);
  - every path dirty now whose hash differs from the snapshot's, or that wasn't in it;
  - every path in the snapshot that is no longer dirty, which catches a deleted untracked
    file and a reverted edit;
- with `--base REV`: every path in `git diff --no-renames --name-status -z REV`, plus
  untracked files. `--no-renames` makes a rename show up as a deletion plus an addition,
  so both sides are listed;
- with neither, or with no snapshot: every path `git status` reports.

Each changed path maps to (D39):
- the router covering it, meaning the nearest router at or above its directory;
- every ancestor router whose text names that path, either relative to the ancestor's
  directory or as the file's name in backticks. Wheelchair's root router names
  `seen/wording.sh` (wheelchair `AGENTS.md:55`), so deleting it must reach the root too.

A rename reaches both sides, because both paths are mapped. Paths that are themselves router
files are dropped. The output is the list of routers, each with the changed paths under it.

`hooks/stop.sh <harness>` is a `Stop` hook on both harnesses:

1. Exit 0 silently on a lane or subagent (as above), or when the input has
   `stop_hook_active: true` (D32).
2. Run `highways sweep --session <session_id>`. Empty list: exit 0 silently.
3. Otherwise print `{"decision": "block", "reason": "<text>"}`. The text names each router
   and its changed paths, and says: read each router against your change; fix anything it
   now says that is false; additions and factual corrections only, never reformat
   (`protocol/sweep.md`); then finish.

Every failure exits 0 silently. No model is called and nothing leaves the machine (D25).

`protocol/sweep.md` carries the rule wheelchair has today (wheelchair
`protocol/implementation.md:218-223`):
- a change that moves ownership between directories updates the routers on both sides;
- an added or removed file updates its directory's router only if that changes what the
  directory owns, or the router named that file;
- a router that is now false is fixed.

It also says that `protocol/routers.md` describes a router being created and is never a
test of an existing one.

### Creation

`create/scan.sh` and its suite move with behaviour unchanged. `protocol/create.md` comes from
wheelchair `protocol/spine.md`, and `protocol/routers.md` from wheelchair's. In both, every
reference to something that exists only in wheelchair is rewritten to its highways equivalent
or dropped (D41):
- the command name (`/spine` becomes `/highways create`);
- the scanner path (`<highways root>/create/scan.sh`, replacing "this repo's `spine/`
  directory" in wheelchair `protocol/spine.md:19-22`);
- the upkeep reference ("the upkeep rule in Stage 3 (`protocol/implementation.md`)" in
  wheelchair `protocol/routers.md:4-7` becomes `protocol/sweep.md`);
- the `protocol/diagrams.md` citation in wheelchair `protocol/routers.md:35-37`, replaced by
  the rule stated inline: never Mermaid, because routers are read in terminals;
- the passage from "This repo is the live case" to "false on arrival." in wheelchair
  `protocol/routers.md:81-84`, which is true only of wheelchair, is dropped. The rule before it
  stays (D48, D49).

The navigation order in `protocol/routers.md` (wheelchair `:57-63`) becomes `highways search →
the routers it names → grep → graphify last`. Check: `grep -nE "wheelchair|/spine|Stage
3|diagrams\.md|implementation\.md" protocol/create.md protocol/routers.md` in highways prints
nothing.

Otherwise the sequence, the pre-write list, the edge-case table and the non-goals carry over
word for word, except that the edge-case row "Second run on a covered repo" (wheelchair
`protocol/spine.md:209`) and the "Re-running on a covered repo" section
(`protocol/spine.md:175-177`) both gain "or the root router lacks the search line" (D41, D46).
Any other line the check below finds, such as `protocol/spine.md:9`'s list of wheelchair's
other commands, is rewritten or dropped too; the check is the authority. Confirmation before any write stays (D2).

### The root-router line

The search line is "If `highways` is installed, run `highways search "<what you're looking
for>"` before reading code to find where something lives." It is conditional because the
router is committed and read by everyone's agents, installed or not (D45). Alongside the pointer row, it is the second permitted addition
to an existing router (D41). Every `highways create` run on a repo whose root router lacks it
proposes it in the pre-write list, including a run on a repo that is otherwise fully covered.
A new root router gets it too. It is never added without confirmation. `protocol/create.md`'s
"Two separate rules about naming children" and "Editing existing content" sections say so
explicitly, so the "one permitted edit" wording doesn't read as forbidding it.

### Install

`install.sh`, idempotent, mirroring wheelchair's installer:
- renders wrappers for each harness found on `PATH`;
- links `bin/highways` into `~/.local/bin`;
- adds `UserPromptSubmit` and `Stop` hook groups to `~/.claude/settings.json` and
  `~/.codex/hooks.json`.

Each group is recognised by its script path and rewritten in place on a rerun, leaving every
other entry untouched. It uses wheelchair `seen/set.sh`'s refusal rules for malformed files.
When the Codex hook entry changes, it prints the `/hooks` approval reminder. Test seams:
`HIGHWAYS_PRESENT`, `HIGHWAYS_CLAUDE_HOME`, `HIGHWAYS_CODEX_HOME`, `HIGHWAYS_CONFIG`
(config path), `HIGHWAYS_STATE` (replaces `~/.cache/highways`), and `HIGHWAYS_DECISIONS_URL`
(points search at a fake server).

### Wheelchair while both are installed (D8, D21)

Wheelchair checks `command -v highways`:
- **Planning:** in Step 1's map step (wheelchair `protocol/planning.md:45`) and in
  `protocol/map.md`, if present, run `highways search` on the change's description first,
  read the routers it returns, then read code.
- **Implementation briefs:** every lane brief the lead writes carries the line "Before
  reading code to find where something lives, run `highways search "<what you need>"`"
  (wheelchair `protocol/implementation.md:75`, where a brief's required parts are listed).
  Lanes run the command; only the hooks skip lanes (D42).
- **Implementation sweep:** the after-lane router sweep (`protocol/implementation.md:218-223`)
  becomes "run `highways sweep --base <the lane's base commit>`; apply highways'
  `protocol/sweep.md` to each router listed". Lanes already run with `WHEELCHAIR_LANE` set, so
  the end-of-turn hook stays out of them.
- **Verification:** the Routers check (`protocol/verification.md:83-85`) is unchanged in what
  it checks and points at highways' `protocol/sweep.md`.

With highways absent, all four are skipped (the planning search, the briefs' line, the sweep,
and the verifier's router check), each saying so in one line. So is the router part of the
post-PASS doc sweep (wheelchair `protocol/verification.md:91`), which with highways present
follows highways' `protocol/sweep.md`. COMPLETION.md's Routers section then reads "highways
not installed; routers not maintained", and the verifier accepts that (D46).
Wheelchair no longer creates or maintains routers itself (D45).

### Removal from wheelchair (D9)

The last phase, done only after the phase 1–5 suites below pass with wheelchair absent from
`PATH`.

Deleted:
- `spine/` (scanner, suite, router);
- `protocol/spine.md` and `protocol/routers.md`;
- `skills/spine/` and `codex/prompts/spine.md`.

Edited to point at highways or to drop the line:
- `AGENTS.md`: the `spine/` row and the `routers.md` mention;
- `README.md:27` and `:119`;
- `CONTRIBUTING.md:54` and `:82`;
- `protocol/AGENTS.md:35`;
- `protocol/implementation.md:218-223`;
- `protocol/verification.md:83-85` and `:91` (the post-PASS sweep's router part);
- `protocol/templates/COMPLETION.md:40-45` (the Routers section gains the highways-absent
  wording);
- `protocol/graphs.md:29`, which defines a router by `protocol/routers.md`;
- `protocol/sensitivity.md:70`, which cites `spine/scan.sh` as an example;
- `skills/AGENTS.md:22`.

`viewer/test/server.test.js:324` uses the path as sample prose and stays. Wheelchair's
`install.sh` removes a previously rendered `spine` skill and Codex prompt from the harness
homes, because its glob alone would leave the old copies installed.

### Phases and validation

0. **Live check (D34, D43).** All three must hold, or stop and set PLAN.md back to
   `planning`:
   - a `noul` request carrying `provider: {"zdr": true}` is answered with a probability (the
     latency is printed);
   - OpenRouter's list of zero-data-retention endpoints
     (`GET https://openrouter.ai/api/v1/endpoints/zdr`) includes the `typesafe/jev` endpoint;
   - Collin confirms that his OpenRouter account's privacy setting is set to allow
     zero-data-retention endpoints only.

   The response alone can't show whether ZDR was applied. The account-level setting makes
   that question moot.
1. **Create.** Run `bash create/test/run.sh`; it must pass unchanged apart from paths.
2. **Search.** Run `python3 -m unittest discover -s test` against a fake Decisions server
   (`HIGHWAYS_DECISIONS_URL`). Cases:
   - wheelchair's `viewer/` case: the root is the answer through `own`;
   - a child answer;
   - a weak non-root parent hides an answer below it (D44);
   - `"mode": "flat"` returns every router whose `own` clears the bar, with no walk;
   - `not-confident`;
   - one failed request makes the search `unavailable`;
   - `not-enabled` and `no-routers` send zero requests (the fake server counts them);
   - every request carries `zdr: true`;
   - the file step keeps only existing named files;
   - the cap of 5;
   - a symlinked `CLAUDE.md` counted once;
   - nothing in the fixture repo changes (hash before and after).

   Fixture routers are built in a temp directory, never committed (IDEA.md Constraints).
3. **Hooks.** Run `bash test/hooks.sh`. Cases:
   - lane, `agent_id` and `stop_hook_active` exits;
   - snapshot diffs: an edit made before the turn isn't blamed on it, a commit during the
     turn is, a rename reaches both sides;
   - garbage input, a missing repo or a missing snapshot all exit 0;
   - no output when nothing routed changed;
   - the per-message hook's context output and the end-of-turn hook's
     `{"decision": "block", ...}` output match each harness's documented shape exactly;
   - a deleted untracked file, a rename, and an ancestor router naming a deleted file are
     each caught;
   - no git command used leaves `.git/index` modified (mtime and hash checked);
   - neither hook writes inside the fixture repo.
4. **Install.** Run `bash test/install.sh` against temp harness homes. It must be idempotent,
   leave other hooks untouched, and refuse malformed files.
5. **Test set.** By hand, in this order:
   - `highways eval draft` for `~/projects/personal/wheelchair` and the work repo's checkout;
   - Collin's review;
   - one `highways eval score` over both files;
   - one `highways eval latency` over both files.

   Commit `search/bars.json`, and nothing else, only after the live run passes every gate.
   Then a live check in each harness: in a temp copy of wheelchair
   with sending on, one message gets the per-message hook's context and one code edit gets
   the end-of-turn hook's send-back. This must pass before phase 6.
6. **Wheelchair integration and removal.** Wheelchair's own suites pass (`bash install/test/run.sh`,
   the codex suite, `npm test` in `viewer/`), and
   `grep -rn "spine/scan.sh\|protocol/spine.md\|protocol/routers.md\|/spine" ~/projects/personal/wheelchair --exclude-dir=docs --exclude-dir=node_modules`
   finds nothing but the viewer test's sample prose.

### Graph verdicts

The four graphs under `graphs/` (`q1-reach`, `q3-search-shape`, `search-flow`,
`q4-upkeep-trigger`) carried no `agreed` or `rejected` entries at the final pass. Their
choices are recorded as D11, D15/D22, D18 and D19/D22–D23.

## Accepted Risks

Real issues consciously not fixed, each with the reason. Part of the spec, not review
scaffolding — an implementer should read these, and later review rounds must not
re-raise them.

| Risk | Why accepted | Round |
|------|--------------|-------|
| Jev's probabilities from separate requests may not compare well enough for one set of bars to work across routers | Only measurable with real calls; the test set measures it, and if the best bars miss the gate in "The test set", the plan goes back to planning rather than shipping looser bars | planning |
| With sending on, the per-message hook sends the text of every message of 4+ words in that repo to Jev through OpenRouter | Collin chose automatic search (D11) and off-by-default sending (D13); ZDR is required on every request (D28, D34) | planning |
| The file step finds named files only when written as backticked paths or link targets; a file named in plain prose is missed | Missing a file only falls back to directory-level answers, never a wrong file | planning |
| Two sessions editing one checkout at once each see the other's edits as their own turn's changes | Over-reporting only means checking an extra router, the safe direction | planning |
| An agent could still turn sending on by editing `~/.config/highways/config.json` directly | D38 stops the command path and `protocol/search.md` forbids it; a deliberate file edit is outside what highways can prevent | review-round-1 |
| A `git pull` during a turn makes the end-of-turn hook list routers for upstream changes the agent didn't make | Over-reporting only means checking an extra router, the safe direction | review-round-4 |
| Subagents get no per-message hook; they find search through the root-router line their harness loads | The root-router line (D41) reaches every agent working in the repo | review-round-1 |

## Review Rounds

### Round 1 — 2026-10-02

**Lanes:** GPT / Sol (gpt-6.1-sol, thread 01a0ffb2-7ba5-7d82-ae01-268069ccf347), mechanics lens; Claude / default reviewer model, intent lens; cross-family: yes.

**Changed since Round N-1:** n/a (first round — whole Spec in scope)

| Lane | Reported | Finding | Lead verdict | Resolution |
|------|----------|---------|--------------|------------|
| Claude | major | With D23, the walk reduces to "every router with own ≥ answer bar"; reach and the walk bar do nothing | user-decision | Q8, settled by Collin as D44 |
| Claude | major | Latency budgets (3 s + 2 s) contradict "well under a second" and nothing gates on latency | upheld | D36 |
| GPT | major | Same latency finding | upheld | D36 |
| Claude | major | No minimum usefulness bar and no measure of reading saved | upheld | D37: answered rate and narrowing gates |
| Claude | major | Commit-subject questions are mostly bookkeeping; merges and docs-only commits not addressed (checked: wheelchair subjects such as "model-pins: COMPLETION citation fix") | upheld | D37: filters plus a person's review |
| Claude | major | No sampling or cost limit, and no score caching across bar settings | upheld | D37 |
| GPT | major | Two eval runs with no pooling; the second overwrites the first | upheld | D37: one pooled score |
| GPT | major | The file bar has no objective it can be tuned on | upheld | D37: file precision and recall |
| GPT | blocking | One right answer plus four wrong extras scores as perfect | upheld | D37: top-wrong and answer precision |
| Claude | major | The root-router line never reaches repos that already have routers; "one permitted edit" reads as forbidding it (checked: wheelchair `protocol/spine.md:131,150-155`) | upheld | D41 |
| Claude | major | The moved format teaches a navigation order without search, and needs more than three edits | upheld | D41 |
| GPT | major | The moved format cites `implementation.md` and `diagrams.md`, absent from highways (checked: `routers.md:4-7,35-37`) | upheld | D41 |
| Claude | major | Implementation lanes are never pointed at search | upheld | D42 |
| Claude | major | `not-enabled` invites the agent to run `highways enable` | upheld | D38, plus an Accepted Risk for direct config edits |
| GPT | blocking | Deleting an untracked file in the snapshot is never detected | downgraded to major | Real, but only in a narrow case; fixed by D40 |
| GPT | blocking | `--name-only` loses a rename's old path | upheld | D40 |
| GPT | blocking | `git status` can write `.git/index` | upheld | D40 |
| GPT | blocking | Nearest-router mapping misses ancestors that name the file (checked: wheelchair `AGENTS.md:55`) | upheld | D39 |
| GPT | major | Phase 0 can't tell honoured ZDR from ignored ZDR | upheld | D43 |
| Claude | minor | Phase 0's fail condition can't be judged | upheld | D43 |
| Claude | minor | Subagents never get the per-message hook | accepted-risk | Accepted Risks |
| GPT | minor | The removal gate never checks hook delivery or creation end to end | upheld | Phase 3 output-shape assertions; live harness check in phase 5 |

### Round 2 — 2026-10-02

**Lanes:** GPT / Sol (gpt-6.1-sol, thread 01a0ffed-3d7f-7b83-95a2-57c831f5d34b), mechanics lens; Claude / default reviewer model, intent lens; cross-family: yes.

**Changed since Round 1:**
- Search: `not-enabled` wording and terminal-only `enable` / `default on` (D38); budgets 1 s and 0.5 s (D36); the walk without D23, plus `mode` (D44).
- "The test set", rewritten: draft → review → score, metrics, gate, cost (D37, D44).
- Per-message hook step 3: `--no-optional-locks` (D40).
- "Upkeep": changed-path rules and ancestor mapping (D39, D40).
- "Creation": every wheelchair-only reference rewritten; navigation order (D41).
- "The root-router line": second permitted addition (D41).
- "Wheelchair while both are installed": implementation briefs (D42).
- "Phases and validation": phase 0 (D43), phase 3 cases, phase 5 live check.
- Accepted Risks: two new rows.

| Lane | Reported | Finding | Lead verdict | Resolution |
|------|----------|---------|--------------|------------|
| GPT | blocking | Phase 2 still tests D23's rescue, which D44 forbids | upheld | Case replaced; flat-mode case added (D45) |
| Claude | major | Same stale D23 case; no flat-mode case | upheld | Same fix |
| GPT | major | Whether the root's own `reach` gates the walk is contradictory | upheld | Root always entered (D45) |
| GPT | major | The offline sweep can try bars below 0.5, where no file scores were cached | upheld | Bar floor of 0.5 (D45) |
| Claude | minor | Same cache-floor gap | upheld | Same fix |
| GPT | major | The latency gate doesn't say whether it times the whole search, and the budgets add up to over 1 s | upheld | Whole-search timing; budgets 0.7 s + 0.3 s (D45) |
| GPT | major | An end-to-end diff misses a change a later commit undoes | upheld | Per-commit `git log` (D45) |
| Claude | major | Narrowing counts a root answer as the whole repo (checked: wheelchair's root covers about 178 of 221 tracked files) | upheld | Own files, or returned files after a file step (D45) |
| Claude | major | The walk-versus-flat rule compares operating points that can't both exist | upheld | Compare best answered rates under the same limits (D45) |
| Claude | major | With highways absent, it's unclear whether the verifier's router check is skipped | upheld | All four skipped; COMPLETION wording given (D45) |
| Claude | minor | The creation check's grep covers new protocol files where mentioning wheelchair is legitimate | upheld | Scoped to `create.md` and `routers.md` |
| Claude | minor | The root line tells teammates without highways to run it | upheld | Line made conditional (D45) |
| GPT | minor | The copied edge-case table says a covered repo gets no proposals, which contradicts the search-line proposal (checked: wheelchair `protocol/spine.md:209`) | upheld | Row amended (D45) |

### Round 3 — 2026-10-02

**Lanes:** GPT / Sol (gpt-6.1-sol, thread 01a0fff4-41a3-7892-832c-40b80088bd0b), mechanics lens; Claude / default reviewer model, intent lens; cross-family: yes.

**Changed since Round 2:** D45 only:
- Search steps 4, 5 and 7 (budgets, root entry);
- the bars' 0.5 floor;
- "The test set" (score caching, narrowing, latency, the walk-versus-flat rule);
- the "Upkeep" session-sweep commit rule;
- "Creation" (grep scope, edge-case row);
- "The root-router line" (conditional wording);
- "Wheelchair while both are installed" (behaviour when highways is absent);
- phase 2 test cases.

| Lane | Reported | Finding | Lead verdict | Resolution |
|------|----------|---------|--------------|------------|
| GPT | blocking | The session sweep's `git log` leaves out merge commits' own changes (checked by the reviewer on a work repo merge) | downgraded to major | Real, but only in a narrow case: a merge made during one agent turn. Fixed: `--diff-merges=first-parent` (D46) |
| GPT | major | Scoring's timing isn't the real search's timing | upheld | A separate latency run of the real search (D46) |
| Claude | major | Budgets during scoring are undefined, and the latency it measures is not the real search | upheld | Same fix; scoring runs without budgets (D46) |
| Claude | major | Narrowing over several answers and unanswered questions is undefined | upheld | Union, answered questions only (D46) |
| GPT | major | A file step that returns nothing gives 0% narrowing | upheld | Falls back to own files (D46) |
| GPT | major | Wheelchair's post-PASS sweep still maintains routers when highways is absent (checked: wheelchair `protocol/verification.md:91`) | upheld | Router part follows highways or is skipped (D46) |
| Claude | major | The covered-repo prose still contradicts the search-line proposal (checked: wheelchair `protocol/spine.md:175-177`) | upheld | Amended (D46) |
| GPT | minor | Same covered-repo prose | upheld | Same fix |
| Claude | minor | The COMPLETION template isn't in the removal list (checked: `templates/COMPLETION.md:40-45`) | upheld | Added (D46) |
| Claude | minor | `spine.md:9` isn't covered by the listed rewrites | upheld | The check is made the authority (D46) |
| Claude | minor | D45 replaced D44's rule without saying so; the walk bar's range isn't stated | upheld | D46 |

Round 3 triage upheld major findings, so it was not clean. Per the three-round cap, this went to Collin rather than a fourth round.

Collin chose a fourth round limited to round 3's fixes (2026-10-02), which resets the cap.

### Round 4 — 2026-10-02

**Lanes:** GPT / Sol (gpt-6.1-sol, thread 01a1000b-1612-7673-be52-096304e661b2), mechanics lens; Claude / default reviewer model, intent lens; cross-family: yes.

**Changed since Round 3:** D46 only:
- the session sweep's merge handling;
- "The test set" scoring (no budgets, 10 s timeout, dropped questions), sweep ranges, the
  narrowing definition, and the separate latency run;
- "Creation" (the covered-repo prose, the check as authority);
- "Wheelchair while both are installed" (the post-PASS sweep's router part);
- "Removal from wheelchair" (`verification.md:91`, `templates/COMPLETION.md`).

| Lane | Reported | Finding | Lead verdict | Resolution |
|------|----------|---------|--------------|------------|
| GPT | blocking | The live latency run checks only speed, so a search that times out everywhere in real use could pass on cached scores | upheld | Gate applies to the live run too (D48) |
| GPT | major | The latency run's temp clone has sending off, so it would time instant `not-enabled` answers | upheld | Temporary `HIGHWAYS_CONFIG` (D48) |
| Claude | major | Same sending-off gap in the latency run | upheld | Same fix |
| Claude | minor | `routers.md:80-83`'s "this repo is the live case" stays false after the move and slips past the grep (checked) | upheld | Dropped (D48) |
| Claude | minor | Narrowing isn't part of choosing the bars, so the plan can fail on a setting another would pass | upheld | Added to selection limits (D48) |
| Claude | minor | A `git pull` during a turn over-reports routers | accepted-risk | Accepted Risks |

Round 4 upheld a blocking finding, so it was not clean. Round 5, scoped to D48, follows; it is the second round since Collin's reset.

### Round 5 — 2026-10-02

**Lanes:** GPT / Sol (gpt-6.1-sol, thread 01a1000f-df46-7a60-a7b6-d662c8af1ac7), mechanics lens; Claude / default reviewer model, intent lens; cross-family: yes.

**Changed since Round 4:** D48 only:
- "The test set": the latency run's config, its live recomputation, the gate checked twice,
  and narrowing among the selection limits;
- "Creation": the dropped live-case passage;
- Accepted Risks: the `git pull` row.

| Lane | Reported | Finding | Lead verdict | Resolution |
|------|----------|---------|--------------|------------|
| Claude | major | Phase 5 never runs `eval latency`, and commits `bars.json` before any live gate | upheld | Phase 5 rewritten (D49) |
| GPT | major | The live gate leaves out answer precision | upheld | The live run checks every metric (D49) |
| Claude | minor | `eval latency`'s arguments and clones are unstated | upheld | Commands table (D49) |
| Claude | minor | Citation off by one, and the passage's last sentence wasn't covered (checked: `routers.md:81-84`) | upheld | Corrected (D49) |

Round 5 upheld major findings, so it was not clean. Round 6, scoped to D49, is the third and last since Collin's reset.

### Round 6 — 2026-10-02

**Lanes:** GPT / Sol (gpt-6.1-sol, thread 01a10012-b78a-7c31-9fa6-3f7135ebcef3), mechanics lens; Claude / default reviewer model, intent lens; cross-family: yes.

**Changed since Round 5:** D49 only:
- the Commands table's `eval` rows;
- "The test set": the live run's metrics and the full gate list;
- "Creation": the dropped passage's citation;
- phase 5's steps.

| Lane | Reported | Finding | Lead verdict | Resolution |
|------|----------|---------|--------------|------------|
| Claude | major | No rule picks the file bar, and a file step returning nothing passes as 0 ÷ 0, so search could ship never naming a file | user-decision | Q9, settled by Collin as D51 |
| GPT | major | The live file-precision gate has no rule for zero returned files | user-decision | Q9, settled by Collin as D51 |
| Claude | minor | Question files don't record which repo to clone | upheld | D50 |
| Claude | minor | `score` puts unvalidated bars in the working tree before the live gate | upheld | D50 |

Round 6 is the third round since Collin's reset, and its two majors are one genuine fork, so it went to Collin as Q9.

Q9 settled by Collin (D51). Round 6 triage upheld no blocking or major finding, and no user-decision is still open, so it is clean. The Spec diagrams were drawn and the plan was marked approved on 2026-10-02.


## Prior Work

| Spec item | State | Evidence (file:line) | Confidence |
|-----------|-------|----------------------|------------|

## Implementation Tasks

| # | Objective | Ownership boundary | Lane | Session id | Validation | Status |
|---|-----------|--------------------|------|-----------|------------|--------|

## Log
