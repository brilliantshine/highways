# The router format

A router is a short `AGENTS.md` or `CLAUDE.md` that says what a directory owns, what
must never happen there, and where to go next. `/highways create` (`protocol/create.md`) creates
and extends routers; the upkeep rule (`protocol/sweep.md`) keeps
them true as ownership moves between directories. Both read the format from this file
rather than each carrying their own copy.

This format was drawn from one repository carrying routers 20 directories deep, called `almanac`
throughout. Every claim below is grounded in it — the observations are real, the name is a stand-in.

## Guidance for creation, never a conformance test

Say this first, because it is the rule most likely to be broken by an agent reading the
list that follows: **an existing router is never measured against this format.**
almanac's own `tests/AGENTS.md` has no ancestor link, states no single
organizing idea, titles its boundaries "Rules," and opens with verification commands
instead of a title — and it is correct as it stands. A `/highways create` run that wants to bring
it into line with the format below is wrong, not thorough.

## What a created router carries

- A title naming the directory and what it is, one line.
- A link to the nearest ancestor router, when one exists — almanac calls this
  field `Owned by`. Not a literal `../`: the nearest directory upward that actually has
  a router, however many levels that is. `src/almanac/AGENTS.md:3` links
  `../../AGENTS.md`, skipping `src/`, which has none. Include the link only when an
  ancestor router exists — it appears in exactly 1 of the 20 reference routers
  (`records/timeline/AGENTS.md:3`), so do not write it as if it were the usual
  case.
- One organizing idea, stated as a rule the directory obeys.
  `records/timeline/AGENTS.md:6` states it as "vague time never becomes metric
  time."
- The flow, when the directory has one, as a plain arrow chain in a fenced block. Never
  Mermaid, because routers are read in terminals.
- A file-to-role table naming the directory's entry points and the files that carry a
  constraint — not every file. One line each, the constraint rather than the
  implementation. A forty-file package gets the handful a reader must know about; this
  selection is what keeps the table from becoming the exhaustive list the hard rules
  below prohibit.
- Boundaries: what must never happen here, and why, one reason each.
- A line for each immediate child directory that has no router of its own.
- Test pointers.

A root router carries all of the above, plus the concept that explains the whole
layout, a directory-to-router table, the navigation order, a graphify policy section,
and verification commands.

## No line cap

The reference runs 22 to 133 lines. State that range as orientation, never as a rule —
the root router at 133 lines fails any cap a leaf would pass, and a root router carries
strictly more than a leaf by design.

## Navigation order

`highways search → the routers it names → grep → graphify last`. Insert a module-docstring rung between router and grep
only where the target repo actually has that convention, evidenced by a count the
router itself states. almanac's root justifies its rung on "~86% of modules in
`src/` carry constraint docstrings" (`AGENTS.md:62`) — something that repo built
deliberately, not a property code has in general.

## The graphify policy section

A root router's graphify section states:

- routers are the spine, and graphify is an opt-in supplement;
- graphify must never answer "where does X live" or "what owns Y";
- a stale graph misroutes silently instead of failing, so a reader checks freshness
  before trusting it;
- graphify earns its place only on blast radius, distance between far-apart concepts,
  and community structure — every result confirmed in source, never taken as fact.

The per-clone claim — that the graph is gitignored and so cannot carry a contract — is
stated only when it is true. `graphify-out/` is gitignored in almanac
(`AGENTS.md:87`) but not everywhere. A `/highways create` run either adds `graphify-out/` to the
target repo's `.gitignore` as part of its own work, surfaced in the pre-write list like
any other change, or it omits the sentence — it never asserts an ignore rule it did not
verify.

## Hard rules

No line numbers. No exhaustive file lists for large packages. Ownership and boundaries,
not implementation. No Mermaid.

The first two are the staleness failure almanac designed this format against
on purpose (`AGENTS.md:123,127-128`): a line number shifts on the next edit and a file
list drifts the moment a file is added or removed. A router that lies is worse than no
router, because someone acts on it.
