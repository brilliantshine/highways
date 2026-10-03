# highways

Router documents for a repository (what each directory owns, what must never happen there,
and where to go next), plus a fast way for an agent to use them to find the right area
before reading code. Works on its own, and alongside [wheelchair](../wheelchair).

It does three jobs, in any git repository:

- **create** — `/highways create <path>` proposes routers and writes them only after you
  confirm (`protocol/create.md`).
- **keep true** — an end-of-turn hook sends the agent back, once, to check the routers its
  change touched (`protocol/sweep.md`; `highways sweep` lists them on demand).
- **search** — `highways search "<what you're looking for>"` asks every router at once and names
  the few places likely to hold the answer, or says it isn't confident (`protocol/search.md`).
  A per-message hook runs the same search on your message and speaks only when confident.

Search sends router text and your question to Jev through OpenRouter, with zero data retention
required on every request. Sending is off by default and switched on per repo, only from your
own terminal: `highways enable [PATH]` (and `highways disable [PATH]`). It needs
`OPENROUTER_API_KEY`.

Install: `./install.sh` — links `highways` into `~/.local/bin`, installs `/highways` for Claude
Code and Codex, and adds the two hooks (run `/hooks` in Codex once to approve them).

How well search works, measured on 113 reviewed questions from wheelchair and mechanical-quill
(2026-10-03): it answers about half of them (48.5%), puts the right place first 98% of the time
when it does, never answered a message that had no answer, and takes 0.42 s typically. Details in
`docs/plans/router-search/`.
