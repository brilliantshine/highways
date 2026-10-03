# `/highways create` — backfilling routers

Documentation-only. `/highways create` proposes router documents (`AGENTS.md`/`CLAUDE.md`) for a
directory tree and writes them only after a person confirms. There is no plan document
and no review gate — the confirm step in the sequence below is the only control.

**Input is a path to a working tree.** This command takes an absolute or relative path to the
directory it should scan.

`protocol/routers.md` holds the format a router should have. This file holds the run
sequence.

## The sequence

1. Run the scanner by absolute path:
   `<highways root>/create/scan.sh <path>` — you are reading this file at
   `<root>/protocol/create.md`, so the highways root is that path with `/protocol/create.md`
   dropped. `highways scan <path>` is an equivalent command once installed.
   Absolute, because `/highways create` runs with a foreign repo as its working directory — the
   same reason every wrapper in this repo hardcodes the absolute path to `protocol/`.
2. If it refused (exit 1), report the refusal as it stands and stop. The target is not
   inside a git repository; the refusal names every immediate child that is a git
   repository or a worktree hub carrying `.repo.git`, and for each hub its lanes, so the
   next command is obvious — point `/highways create` at one of those. Do not walk in: handling a
   workspace directly means deciding which branch a router belongs on, a branching
   question rather than a router one.
3. Classify each candidate directory against "which directories earn a router," below.
4. Draft what would be written.
5. Present the full pre-write list and stop.
6. On confirmation, write. Nothing is written before this step.

## The scanner's output

`scan.sh` writes JSON to stdout and writes nothing anywhere. Every key is always
present; an absent value is `null` or `[]`, never omitted. Its shape, so the procedure
is readable without opening the script:

```json
{
  "target": "/abs/path", "gitToplevel": "/abs/path", "ok": true, "refusal": null,
  "directories": [
    { "path": ".",
      "candidates": [ { "name": "CLAUDE.md", "isSymlink": true, "resolves": "AGENTS.md",
                        "broken": false, "resolvesOutsideTarget": false,
                        "size": 8292, "headings": ["# title", "## Layout"] } ],
      "realCount": 1, "writeTarget": "AGENTS.md",
      "identical": false, "diffLines": null, "skipped": null,
      "unmanagedSurfaces": [], "notes": [] }
  ],
  "excluded": [ { "path": "node_modules", "reason": "git-ignored" } ]
}
```

`writeTarget` is the real file, resolved through any symlink — it is never a link path.
It is `null` when the directory has no candidate yet, when it holds two real files, or
when the directory was skipped. A refusal replaces `refusal` with a reason plus
`repositories` and `hubs` arrays, and the script exits 1.

The script deliberately leaves two judgments to the prompt, because both were tried as
code and both broke on the calibration repo:

- **Which of two real routing files is the router.** `scan.sh` never decides this and
  never aborts on finding two — it reports both, with sizes, heading lists, and a
  unified-diff line count between them. Encoding the choice was tried twice, once as a
  substantive-versus-pointer distinction and once as an exact length-and-content
  grammar, and both aborted on almanac's own root, which holds a real
  8292-byte `AGENTS.md` beside a real 199-byte `CLAUDE.md` that is three lines of prose
  around a link. Whether a file *contains* a router or *points at* one is a judgment.
  The prompt says which file it believes is the router and why; the pre-write list
  carries that choice; the person confirms it.
- **The filename for a new router.** Nothing is inferred. Inheriting the nearest
  ancestor's filename was tried and removed — one directory on this machine documents
  that the symlink direction inverts below it, so inheritance would name every child
  repo's router backwards. The pre-write list states the filename each new router will
  use, and why, and the confirm step settles it.

A heading list is a **human-readable summary, not a byte-faithful channel.** It exists so the
prompt can tell a real router from a pointer beside it, and both of those are ordinary markdown.
The scan does not promise that two files render distinguishably: a malformed byte is shown as a
visible marker, and ordinary valid text can produce the same marker. A candidate **whose headings** carry
bytes that cannot be represented is flagged in its directory's `notes` and its heading list
declared unreliable, so the reader goes and looks instead of trusting a rendering that lost the
difference. Scoped to the headings because they are what the report carries: a malformed byte
elsewhere in the file affects nothing it says. NUL is the exception and is checked against the
whole file, because bash drops it before any rendering could report it. Chasing a collision-free encoding instead cost three
remediation rounds and produced two representations that were each claimed collision-free and were
not.

Heading lists and a diff line count are reported instead of opening lines, because
opening lines are exactly what fails on the case this evidence exists for: one real
pair of drifted routers on this machine shares byte-identical first three non-blank
lines and differs by 35 insertions further down. A heading list shows which file is the
superset and where the extra material sits; a diff count shows how far apart they are.

## Which directories earn a router

A directory earns one when it has a rule of its own — a boundary a reader must know
before editing there, an ownership claim, or a convention differing from its parent. A
directory that merely groups files does not earn one, and a directory never earns one
because a descendant did.

That judgment is the prompt's. The confirm step checks it by one guard: for each
proposed router, the pre-write list states the one boundary sentence the parent does
not already state. A proposal that cannot produce that sentence is not a router. There
is no ratio, no threshold, and no second mechanism — say so plainly, so nobody adds one
later.

Ground this in the reference: almanac's `tests/` tree is 33 directories
carrying exactly 2 routers. Any rule that reduces to a blocklist of caches and build
output yields about 31 routers there — the router-per-folder outcome the idea behind
this command rules out.

## Two separate rules about naming children

These were conflated once and it broke both. Keep them visibly distinct.

**Coverage naming — created routers only, immediate children only.** A router
`/highways create` creates names its immediate child directories that did not earn their own, one
line each. This is the mechanism the reference uses to hold 2 routers across 33 test
directories: `tests/AGENTS.md`'s Layout table names every non-earning child in one
line. Immediate only — the reference root names `docs/` and nothing beneath it, though
`docs/` holds ten tracked descendants.

For an existing router, a child that earned no router is reported as an observation
and never edited in. `tests/AGENTS.md` names eight children while two tracked
descendants go unnamed; adding those would be measuring an existing file against the
format, which this command does not do. Surfacing and leaving alone is the resolution.

**The pointer row — one of two permitted edits to an existing router.** When `/highways create`
creates a router, the nearest ancestor router that has a directory table gains one row
pointing at it. Depth is not a constraint here and must not be: the reference root
table lists a path four levels down, because a directory table exists for reachability
from the entry point, not to describe adjacency. Across all 20 reference routers the
only directory tables are the root's, `tests/AGENTS.md`'s and
`tests/invariants/AGENTS.md`'s — so for any package under `src/` the nearest ancestor
holding one is unambiguously the repo root.

The guard: the row is added only when the ancestor already has such a table, only
pointing at a router this run created, and nothing else in the file changes. Where no
ancestor has a table, the omission is reported and nothing is edited — inventing a
table would be reformatting.

This edit is permitted at all because a table that omits a router which now exists is
factually wrong, and correcting facts is the one edit to an existing router the rule
below already allows. It is also the only thing keeping a created router reachable
from the entry point.

**The root-router search line — the other permitted edit to an existing router.** The
root router carries one line: "If `highways` is installed, run `highways search "<what
you're looking for>"` before reading code to find where something lives." It is
conditional because the router is committed and read by everyone's agents, installed or
not. A new root router gets it. Every run on a repo whose root router lacks it proposes it
in the pre-write list, including a run on a repo that is otherwise fully covered. It is
never added without confirmation, and nothing else in the file changes.

## Editing existing content

Existing content is extended and corrected, never reformatted. The only permitted
edits to an existing file are additions and factual corrections — in practice the pointer
row and the root-router search line above, and nothing beyond them. Reordering sections,
rewriting prose that is still true, and normalizing toward the format in
`protocol/routers.md` are all out of scope.

## The pre-write list

Everything, before anything is written:

- every file to create or extend, and what changes in each
- the one boundary sentence per proposed router that its parent does not already state
- the filename chosen for each new router, and why
- which candidate it believes is the router in any directory holding two, and why —
  the judgment `scan.sh` deliberately does not make, surfaced here for a person to see
- every directory that earned no router
- any unmanaged surface found (`GEMINI.md`, `.cursorrules`) — reported so the person
  knows it may drift; never read, never written
- every excluded directory with its reason
- any row it will add to an ancestor router's directory table
- the root-router search line, when the root router lacks it (or is being created)
- any `graphify-out/` addition to `.gitignore`

Then stop and wait.

## Re-running on a covered repo

A second run proposes nothing unless a directory now lacks a router it should have, or the
root router lacks the search line.
Detecting stale references inside existing routers is not attempted — the extraction
had no resolution rule and false-fired on the reference repo, where one router names
paths in a Source column that do not resolve against its own directory. A router going
stale is caught by the upkeep rule at the moment the change is made, which is where it
belongs.

## Edge cases

| Case | Behavior |
|---|---|
| Target is not inside a git repository | Refuse, naming every immediate child that is a git repository or a `.repo.git` hub, with each hub's lanes listed. This is the workspace-root case |
| `CLAUDE.md` is a symlink to `AGENTS.md` | `AGENTS.md` is the write target; the link is untouched |
| `AGENTS.md` is a symlink to `CLAUDE.md` | `CLAUDE.md` is the write target; the link is untouched |
| Two real routing files in one directory | Both reported with sizes, heading lists, and a unified-diff line count. The prompt proposes which is the router and why; the person confirms. Never an abort |
| Two byte-identical routing files in one directory | Reported as a duplicate for consolidation. The script picks nothing |
| A nested git working tree or submodule inside the target | Excluded from the walk and reported as a nested repository. Never a candidate |
| A child directory that is a **symlink** | Excluded and reported as such; the walk never follows it. A link pointing inside the target aliases a directory the walk already reaches by its real path, and one pointing outside would otherwise have `/highways create` proposing routers in a tree nobody named |
| A candidate whose **headings** carry bytes that cannot be represented, or whose content carries NUL | Flagged in the directory's notes, heading list declared unreliable. The rendering is not guaranteed to distinguish it from another such file, which is why the flag exists. A malformed byte in the body only is deliberately not flagged — nothing the report carries is affected by it |
| A path that is not valid UTF-8 | Excluded and reported with that reason. JSON is defined over Unicode text, so emitting the bytes would make the whole report unparseable |
| Symlink broken, or resolving outside the target tree | Skip the directory and report. Never follow or repair |
| Existing router in a foreign style | Additions and factual corrections only. Never reformatted, never measured against the format |
| Existing router omits a child that earned no router | Reported as an observation. Not edited |
| Existing ancestor router has a directory table and `/highways create` creates a router below it | One row added pointing at the new router. Nothing else in the file changes |
| Existing ancestor router has no directory table | Reported, not edited. Adding a table would be reformatting |
| Directory owns no rule | Earns no router. Named by the router `/highways create` creates above it, if it creates one |
| Directory is excluded (git-ignored or dotted) | Not considered, reported with its reason |
| A reachable unmanaged surface (`GEMINI.md`, `.cursorrules`) | Reported. Never read, never written |
| Nearest ancestor router is several levels up | That is the link target. No intermediate router is created |
| No ancestor router anywhere | The root gets one first, so children have something to link |
| Filename for a new router | Stated in the pre-write list with its reasoning. Never inferred |
| `graphify-out/` not gitignored in the target | Add the rule as part of the run, or omit the per-clone sentence. Never assert it unverified |
| Second run on a covered repo | Empty write list unless a directory now lacks a router it should have, or the root router lacks the search line |

Each row exists because a specific reading of the rules above went wrong; do not
collapse rows that look similar.

## Non-goals

Four bind the whole command and are stated in their own sections above, gathered here so
a reader looking for the boundary finds it in one place: no rewriting or reformatting an
existing routing document, no measuring one against `protocol/routers.md`, no writing
anything before a person confirms, and no walking into a workspace root or lane
checkout.

Five more were removed during review of the plan behind this command, and do not come
back:

No coverage ratio or any threshold on how many routers a tree should have. No
denominator distinction between excluded and covered directories. No filename
inference from an ancestor router. No extraction of the paths and children an existing
router mentions. No stale-reference detection on a re-run.

Each of those five existed once to enrich the report `/highways create` produces, and between
them they produced a defect in three consecutive review rounds of the plan this command
implements.
