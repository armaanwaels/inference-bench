# Commands for Armaan to run

Since Nov 26, 2026 GPU steps run through the GitHub Actions workflow described in the "GPU runs"
section of `PLAN.md`. The workflow runs them on Modal and commits the result files to
`autopilot`. This file now holds only what cannot be done through that workflow. The autopilot
itself still has no GPU and no keys. Until result files are committed, no number from them
appears anywhere in this repository.

## How entries are written

Each entry has:

- **Added**: the date and the slice that added it.
- **Why the workflow cannot do it**: one line.
- **Needs**: what must be set up first (for example a Modal login, done by Armaan on his machine).
- **Commit to run from**: the commit the commands were written for.
- **Commands**: copy and paste, in order. The first command of every entry prints the plan and
  the cost estimate and spends nothing.
- **Expected files**: the exact paths that should exist afterwards.
- **Then**: what to commit, and on which branch. Add a row to `results/SPEND.md` for any GPU time
  used, so the budget total stays right.
- **Status**: open, or done with the date and the commit that added the files.

## Entries

None. Nothing is waiting for Armaan.

## What could land here

- The workflow cannot reach Modal or cannot push to `autopilot` (a secret is missing or expired,
  or Actions lacks write permission). LOG.md will say so at the top, and the fix or the fallback
  commands will be listed here.
- A run that needs more than the workflow allows (above 60 GPU minutes in one request, or another
  GPU type).
- The upstream patch. It is not a command list: Armaan writes and submits it himself, from the
  notes in `UPSTREAM.md`.
