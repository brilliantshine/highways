---
slug: router-search
status: draft   # draft | confirmed
created: 2026-10-02
---

# Find the right part of a repo fast, from its router documents

## What we're building

Highways is a standalone tool that owns router documents for a repository: the short
`AGENTS.md`/`CLAUDE.md` files saying what each directory owns, what must never happen there,
and where to go next. It creates and updates them, taking over the job wheelchair's `/spine`
does today. It also adds what's missing now: a fast search that uses those routers to narrow a
question ("where is the code that handles X?") down to a few directories in well under a second.
It does that with a fast decision model such as Jev, not by reading everything. It works on its
own in any repo, and wheelchair uses it when both are installed.

## Why — the problem

Wheelchair keeps routers true. Its implementation stage updates them, and its verifier checks
them. But no agent is ever told to use them to decide where to look, so they cost upkeep and
earn little. Agents still find their way by grepping and reading files, which is slow and uses
up context on code that turns out not to matter. A router already says, in a few lines, what a
directory is for. What's missing is a quick way to ask all of them at once.

## What good looks like

- An agent with a question about a repo asks highways first, and gets back a short ranked list
  of directories with how confident each one is, fast enough that asking is always worth it.
- The agent reads only those directories' routers and code, and finds what it needed with
  noticeably less reading than grepping the whole repo.
- When highways isn't confident, it says so, and the agent falls back to grep as it does today.
  It never sends an agent confidently to the wrong place.
- Creating and updating routers works as `/spine` does today, from highways alone, in any repo.
- With both installed, wheelchair's stages (mapping code, planning, implementing) use highways
  to find their way. Wheelchair's router upkeep and checks keep working, pointed at highways.
- Without wheelchair, highways is still complete: router creation, upkeep and search.

## Not doing

- Not moving the router pieces out of wheelchair yet. `/spine`, the scanner and the router
  format stay in wheelchair until highways can do their job. Removing them from wheelchair is a
  later step.
- Not replacing grep or reading code. Highways narrows where to look; the agent still reads.
- Not a knowledge graph, and not an index of every file or symbol. It works from the routers,
  which people keep true, not from an automated index that goes stale silently.
- Not writing routers without a person confirming, the same rule `/spine` follows today.

## Constraints

- Works standalone, and works seamlessly with wheelchair. Neither may require the other.
- A router that lies is worse than no router. Anything that writes one leaves it true or leaves
  it alone, and never writes through a symlink.
- Both Claude Code and Codex load `AGENTS.md`/`CLAUDE.md` as live instructions, so nothing
  example-like or test-only may be committed as a router inside a repo.
- Jev's API, access, cost and accuracy haven't been checked yet (MAP.md). The design can't
  depend on details nobody has confirmed.
