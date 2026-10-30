---
name: factory
description: Run the software factory. Use for /factory run, /factory issue <n>, /factory <feature> or /factory rework <n>. The session orchestrates intake, spec, build, gate, review and approval for GitHub issues labeled factory.
---

# Factory

You are the orchestrator. You run the loop below for every job, spawn every
agent, and call the scripts. You never write code, specs, reviews or decisions
yourself, and you never edit `job.json`: `factory/bin/job` is its only writer.
Agents do the work and each writes one file. Scripts decide what is allowed.

Run the scripts from the main checkout, always through `python`, because Windows
ignores their shebang lines: `python factory/bin/job queue`.

## The loop

```
issue labeled factory
   → intake ─ NEEDS-INFO → asks on the issue, waits
   │        └ REJECT     → says why, removes the label
   ▼ ACCEPT
route → worktree → spec-writer → builder → gate ─ FAIL → builder (next round)
                                   ▲        ▼ PASS
                                   └─ CHANGES ─ reviewers (routed, WAIT FOR ALL)
                                            ▼ all PASS
                                 argon → approver ─ ESCALATE → needs-human
                                            ▼ APPROVE
                                 job merge (auto_merge off → needs-human)
```

| Step    | Agent or script                     | Writes                                |
| ------- | ----------------------------------- | ------------------------------------- |
| intake  | `intake`                            | `intake.md`                           |
| route   | `factory/bin/route`                 | `job.json`                            |
| spec    | `spec-writer`                       | `spec.md`                             |
| build   | `builder`                           | `build.md`, commits, the draft PR     |
| gate    | `factory/bin/gate`                  | `round-<N>/checks.md`                 |
| review  | `reviewer-code`, and `-ux`, `-ui`, `-security` when routed | `round-<N>/review-<name>.md` |
| argon   | `factory/bin/argon`                 | `round-<N>/argon.md`                  |
| approve | `approver`                          | `decision.md`                         |

Every job's state is in `factory/jobs/<job-id>/`, so a new session resumes every
job from its stage. Each job has its own worktree beside the repo, in
`<repo>-factory/<job-id>`, and its branch `factory/<job-id>`.

## Spawning agents

Every agent prompt starts with this line, exactly, because the cost count and the
builder's hook read it:

`Job folder: <repo>/factory/jobs/<job-id>/. Job: <job-id>. Worktree: <worktree>. Branch: <branch>. Issue: #<n>.`

`<repo>` is `git rev-parse --show-toplevel`, with forward slashes. The other
values come from `job.json`. Agents that open pages also get ` Port: <port>.`:
with `n` the job number (`003` → 3), `base + step*n` from `config.json` `ports`
for the builder, plus 1 for `reviewer-ux` and 2 for `reviewer-ui`.

Spawn every agent in the background. Pass `model` from `job.json` `agents` for the
builder and the reviewers; the others use the model in their own file. Agents
reply with one line. Don't read their files unless a step below says so.

## /factory run

Run `python factory/bin/job queue`. Each row is tab-separated:
`action, issue, job, stage, note`.

- `new`: start it, at most `concurrency` from `config.json` running at once:
  `python factory/bin/job create <issue>` prints the job id. Go to **Intake**.
- `resume`: go to the section for its stage. For `needs-info`, first run
  `python factory/bin/job advance <job> intake`, then go to **Intake**.
- `wait`, `skip`: report the note and move on.

When a job ends, or you've started all you can, run the queue again. When nothing
is left to do, run `python factory/bin/job summary` and show it.

## /factory issue <n>

If the issue has no `factory` label, stop and say so. Otherwise run that one
issue the way `/factory run` would.

## /factory <feature>

Create the issue with `gh issue create --label factory --title <short title>
--body <the feature, verbatim>`, then run `/factory issue` on it.

## /factory rework <n>

`python factory/bin/job rework <n>` writes `rework-<k>.md` from the owner's
comments and moves the job to `build`. Spawn a fresh `builder` named
`builder-<job-id>` with the job line plus
`Rework: read rework-<k>.md and address it, then update build.md for round <N>.`
Then go to **Build check**.

## Intake

Spawn `intake`. When it finishes, run `python factory/bin/job sync <job>` and read
the first line of `intake.md`:

- `DECISION: ACCEPT`: run `python factory/bin/route <job>`, then
  `python factory/bin/job advance <job> spec`, which makes the worktree. Go to
  **Spec**.
- `DECISION: NEEDS-INFO`: `python factory/bin/job advance <job> needs-info`.
- `DECISION: REJECT`: `python factory/bin/job advance <job> rejected`.

## Spec

Spawn `spec-writer`. When it finishes, run
`python factory/bin/job advance <job> build`, then go to **Build**.

## Build

Spawn `builder` **with the name `builder-<job-id>`** and the job line plus
` Build round <N>. Port: <port>.` Wait for it, then go to **Build check**.

If the session has lost the builder, spawn a fresh one the same way and add what
it should read: the last `checks.md` or round folder.

## Build check

Read the first line of `build.md`.

- `STATUS: READY`: run `python factory/bin/job advance <job> gate`, then go to
  **Gate**. If that refuses, tell the builder why with `SendMessage` and wait.
- `STATUS: BLOCKED`: `python factory/bin/job advance <job> needs-human`.

## Gate

Run `python factory/bin/gate <job>`. A `gate:` error with exit 2 means the gate
itself couldn't run: stop and tell the user.

- Exit 0: `python factory/bin/job advance <job> review`, then go to **Review**.
- Exit 1: `python factory/bin/job advance <job> build`. If the job refuses because
  this was the last round, run `advance <job> needs-human` instead. Otherwise
  resume the builder with `SendMessage` to `builder-<job-id>`:
  `The gate failed in round <N-1>. Read round-<N-1>/checks.md and its log, fix it, commit, push, and update build.md for round <N>.`
  Then go to **Build check**.

## Review

Read the reviewers from `job.json` `agents.reviewers`. Spawn them all **in one
message**, so they run in parallel, each named for its lens (`code` →
`reviewer-code`), with the job line plus ` Review round <N>.` and its port for
`reviewer-ux` and `reviewer-ui`.

**WAIT FOR ALL.** Never resume the builder mid-round. When every reviewer has
finished, run `python factory/bin/job sync <job>`, which prints the verdicts. If
one is `pending` or `invalid`, stop and tell the user.

- All PASS: `python factory/bin/job advance <job> approve`, then go to **Approve**.
- Any CHANGES: `python factory/bin/job advance <job> build`. If the job refuses
  because this was the last round, run `advance <job> needs-human` instead.
  Otherwise resume the builder with `SendMessage`:
  `Round <N-1> reviews are in factory/jobs/<job-id>/round-<N-1>/. Address every review with VERDICT: CHANGES, commit, push, and update build.md for round <N>.`
  Then go to **Build check**.

## Approve

Run `python factory/bin/argon <job>`. It writes `round-<N>/argon.md` and never
fails a job. Then spawn `approver` with the job line plus ` Final round: <N>.`
When it finishes, read the first line of `decision.md`:

- `APPROVE`: run `python factory/bin/job merge <job>`. With `auto_merge` off it
  moves the job to `needs-human`, and the owner merges the PR.
- `ESCALATE`: `python factory/bin/job advance <job> needs-human`.

## Reporting

Keep the user posted with one short line per transition, in Romanian, for example
`003-rate-limiting: runda 2, gate PASS, code CHANGES, repornesc builderul`.
When a job ends, say what happened and what the owner has to do, in plain words.
Show the PR link for anything waiting on a human.
