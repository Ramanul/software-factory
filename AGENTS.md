# AGENTS.md — software-factory

Rules for every agent working in this repo.

## What this repo is

The software factory and the small tools it builds. The owner, Alexandru, doesn't
program, so tests and scripts stand in for his review. It's public, has no site,
and nothing in it is ever deployed.

## Hard limits

- Never deploy, publish or host anything. No GitHub Pages, no hosting config, no
  workflows under `.github/`.
- Work only in this repo and its worktrees. Never touch another project on this
  machine or on the owner's GitHub account.
- Never commit secrets, tokens, personal data or local paths with a username.
  `factory/argon.local.json` and `.claude/settings.local.json` stay ignored.
- `factory/bin/guard` blocks shell commands that cross these limits, and
  `factory/bin/gate` fails a branch that does. Don't work around either.

## Setup

A fresh checkout needs Python 3.10 or later, Git Bash and an authenticated `gh`.
There are no dependencies to install and no env files to copy. On Windows every
script runs through `python`: `python factory/bin/job queue`.

## Dev server

None. If a job adds a page, serve it with `python -m http.server <port>` from the
folder that holds it.

## Validation

`bash factory/checks.sh`, which validates `factory/config.json` and runs
`python -m unittest discover -s tests`.

## Conventions

- Python standard library only, unless a spec says otherwise.
- Files are UTF-8 with LF line endings. Pass `encoding="utf-8"` when opening text.
- New tools go in their own folder at the root, with their tests under `tests/`.
- Text people read is in Romanian. Code, commits and identifiers are in English.

## Software factory

`/factory run` builds every open GitHub issue labeled `factory` through
intake → spec → build → gate → review → argon → approve, one PR per issue. State
is in `factory/jobs/` (gitignored); `factory/bin/job` is its only writer. Checks:
`factory/checks.sh`. Dashboard: `cd factory && python -m http.server`, then open
http://localhost:8000/dashboard.html.
