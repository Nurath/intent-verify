# Working logs

One file per working day, `YYYY-MM-DD.md`: what was done, what was measured,
what is still open. The date is the H1.

## Why this exists

The other documents describe the plugin as it is. These describe how it got
there on a given day, which is what a new session needs in order to continue
without the conversation that produced it:

- `docs/handoff_quickstart.md` — where to start; read it first.
- `docs/architecture.md` — what the system is.
- `CHANGELOG.md` — what each release changed, for users.
- `logs/YYYY-MM-DD.md` — what we did that day, including what failed, what was
  left unverified and why.

Reading the newest one or two logs should give the same "where are we" as
scrolling back through the session.

## Conventions

Use the headers that fit the day; skip the rest.

- `## Why` — what prompted the work
- `## Changes shipped` — what changed and the reason, by area, with the PR
- `## Tests / verification` — what was run and what it showed
- `## Measurements` — numbers, with how they were obtained
- `## Not verified` — what could not be checked, and what blocked it
- `## In flight / follow-ups` — what to pick up next
- `## Notes` — anything that will surprise the next person

This repository is public and its files are installed with the plugin. Nothing
private goes in a log: no local paths, no other projects, no prompt text.
