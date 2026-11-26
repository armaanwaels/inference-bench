# Commands for Armaan to run

The autopilot has no GPU and no keys. Every step that needs a GPU or a model API is listed here
as exact commands with the files they should produce. Armaan runs them and commits the result
files. Until those files are committed, no number from them appears anywhere in this repository.

## How entries are written

Each entry has:

- **Added**: the date and the slice that added it.
- **Needs**: what must be set up first (for example a Modal login, done by Armaan on his machine).
- **Commit to run from**: the commit the commands were written for.
- **Commands**: copy and paste, in order. The first command of every entry prints the plan and
  the cost estimate and spends nothing.
- **Expected files**: the exact paths that should exist afterwards.
- **Then**: what to commit, and on which branch.
- **Status**: open, or done with the date and the commit that added the files.

## Entries

None yet. Nothing needs a GPU until the correctness suite can run against a real engine.

Planned entries, so the GPU time can be booked in one sitting after Jan 5, 2027:

1. After slice 15: correctness runs, each engine in default mode and in deterministic mode.
2. After slice 20: repeated benchmark runs of the existing 21 cells.
3. After slice 29: a candidate run set on a newer engine release, then the gate command.
