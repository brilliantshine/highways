---
slug: router-search
---

# How this works today

Router documents and everything around them currently live inside wheelchair
(`~/projects/personal/wheelchair`). This map covers what exists there, how agents actually
use routers today, and what is known about Jev. Every `file:line` below is in the wheelchair
repo unless it says otherwise. Written 2026-10-02, from wheelchair at `a552802`.

## End to end

```
/spine <path> → scan.sh walks the tree (read-only, JSON out) → agent classifies dirs
              → agent drafts routers → person confirms → agent writes AGENTS.md/CLAUDE.md

wheelchair Stage 3 → "sweep the routers" after each lane → routers kept true
wheelchair Stage 4 → verifier checks COMPLETION.md's Routers section

agent working in a repo → harness loads AGENTS.md/CLAUDE.md up the directory tree
                        → nothing tells it to search the routers to decide where to look
```

## What happens

1. `/spine` takes a path, not a plan slug, and sits outside wheelchair's plan state machine
   (`protocol/spine.md:1-11`). The sequence is fixed (`protocol/spine.md:16-32`):
   - run the scanner
   - stop on a refusal
   - classify each candidate directory
   - draft the routers
   - show the full list and stop
   - write only after a person confirms
2. The scanner, `spine/scan.sh` (441 lines), resolves and reports, but never decides and never
   writes (`spine/AGENTS.md:7-10`). It refuses a path outside a git repo, skips ignored,
   dotted and nested-repo directories, and resolves each `AGENTS.md`/`CLAUDE.md` through its
   symlinks so a write never goes through a link (`spine/AGENTS.md:14-17`, `:36-37`). It has
   its own fixture suite, `spine/test/run.sh`.
3. The router format lives in `protocol/routers.md` (94 lines): what a created router
   carries, the navigation order `router → grep → graphify last` (`protocol/routers.md:57-63`),
   and hard rules. It is guidance for creating a router, never a test of an existing one
   (`:12`).
4. Upkeep happens in wheelchair's implementation stage. After each lane, the lead sweeps the
   routers: a change that moves ownership between directories updates the routers on both
   sides, and a router that is now false gets fixed (`protocol/implementation.md:218-223`).
   Verification checks that COMPLETION.md's Routers section is true
   (`protocol/verification.md:83-85`).
5. A graph prefers a router as its source when one covers the feature
   (`protocol/graphs.md:406-409`).
6. The wrappers are `skills/spine/SKILL.md` and `codex/prompts/spine.md`, one-line pointers to
   `protocol/spine.md`. The installer picks them up by globbing (`skills/AGENTS.md:22`).
7. **How routers get read.** Claude Code and Codex load `AGENTS.md`/`CLAUDE.md` up the
   directory tree as live instructions (`docs/plans/router-spine/IDEA.md`, Constraints). So a
   router is read when an agent happens to be working in or below its directory. No wheelchair
   stage tells an agent to search routers to find where to work:
   - planning's map step says "Read the code the change will touch" (`protocol/planning.md:45`)
   - `protocol/map.md` never mentions routers
   - the instruction "read the router for the directory you are touching" appears only in
     wheelchair's own root `AGENTS.md`, which applies only inside that repo

   This matches Collin's sense that agents update routers but rarely use them.

What is known about Jev, from public articles (not checked by trying it):

8. Jev is a decision model from TypeSafe AI, released 2026-09-15, marketed as a "System One
   model". It answers typed questions about text or JSON (yes/no, choice, score) and returns
   structured values with calibrated probabilities, never prose. The vendor claims 70–500 ms
   latency and $0.042 per million input tokens.

## What matters for this change

- The pieces that move to highways are self-contained: one scanner with its own tests, one
  format document, one sequence document, and two wrappers. Upkeep and verification stay
  wheelchair stages, but they point at `protocol/routers.md`, so after the split they would
  need to point across to highways.
- Writing routers is solved and guarded (the symlink rule, the confirmation step). Reading them
  is the gap: nothing turns "I need the code that does X" into "go to these two directories".
  That is the gap the fast decision model would fill.
- A router is short, structured prose about one directory: what it owns, what it must not
  touch, where to go next. That shape suits typed questions ("does this directory own X? yes
  or no, with a probability") better than open generation.

## Problems found

- Routers stay true in repos where wheelchair's Stage 3 runs, but no rule makes any agent read
  them first. So routers cost upkeep and earn little routing.
- Wheelchair names graphify as the only other routing aid and fences it off (routers first,
  graphify last). Nothing fills the middle: a quick narrowing step between "read one router"
  and "grep everything".

## Not checked

- Jev itself: no API call made, no access confirmed, no pricing or accuracy measured. Point 8
  is the vendor's and press's claims only.
- How many repos on this machine have routers today, and how good they are.
- Whether Codex and Claude Code load routers the same way in every case (nested repos,
  symlinked pairs).
- How a highways search would be invoked from an agent: a CLI, an MCP server, or a hook.
