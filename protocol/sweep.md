# `/highways sweep` — keeping routers true

Documentation-only. Existing routers are corrected without asking, because a router that
says something false is worse than no router.

## When this applies

- The end-of-turn hook sent you back with a list of routers and the paths changed under
  each.
- A person ran `/highways sweep`.
- A caller, such as wheelchair after a lane finishes, ran
  `highways sweep [--base REV] [--session ID]`. It lists the routers covering what
  changed and the changed paths under each, and writes nothing. Acting on the list is
  your job.

## The rule

Read each listed router against the change, then:

- a change that moves ownership between directories updates the routers on both sides;
- an added or removed file updates its directory's router only if that changes what the
  directory owns, or the router named that file;
- a router that is now false is fixed.

A router that is still true is left alone, even if the change touched its directory.

## Limits

Additions and factual corrections only. Never reformat, reorder, or rewrite prose that is
still true. Never write through a symlink: write the real file the link resolves to, and
leave the link untouched. No new router is created here — that is `/highways create`, and
it asks for confirmation first.

`protocol/routers.md` describes a router being created. It is never a test of an existing
one, so do not bring an existing router into line with it.
