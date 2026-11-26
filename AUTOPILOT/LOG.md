# Inference gate: run log

One entry per run, oldest first. Notices that Armaan must see go in the section right below.

## Notices

- **Nov 26, 2026. Go tests cannot run in the cloud run.** `go.mod` asks for Go 1.27.1, the cloud
  run has Go 1.24.7, and the session's network policy refuses the toolchain download (host
  `proxy.golang.org`). This was not worked around. The plan changes no Go code, and GitHub Actions
  runs the Go job on every push to `autopilot`, so each run reads the Actions result and records
  it here. No action is needed for the plan as written. If the cloud run should run Go tests
  itself, allow the Go toolchain download for this environment.

- **Nov 26, 2026. The plan was revised for automated GPU runs.** It now has 37 slices, not 30,
  and ends on Jan 1, 2027 with no lost days (the window closes Jan 25, 2027). GPU steps go through
  a GitHub Actions workflow that a request file starts. The rules are in the "GPU runs" section of
  PLAN.md. No workflow exists yet and nothing has been spent. The first request (a smoke check
  with no GPU) is planned with slice 12, and the first GPU spend with slice 13, estimated at
  0.55 dollars.

## Nov 26, 2026: slice 0, first run (plan and files)

**Done**

- Attached and cloned `armaanwaels/inference-bench`. Push access works. Created the branch
  `autopilot` from `main` at 82ce8d4.
- Read the whole repository: the Go load generator, `bench/matrix.py`, `bench/modal_app.py`,
  `bench/report.py`, all tests, the CI workflow, README, ARCHITECTURE and `results/`.
- Wrote `AUTOPILOT/PLAN.md` (30 slices, then 4 slices that wait for result files),
  `AUTOPILOT/RUN_THESE.md` (no entries yet) and `AUTOPILOT/UPSTREAM.md` (format and two leads,
  no candidates yet).
- Read two public documentation pages to ground the plan: vLLM batch invariance and SGLang
  deterministic inference. Links are in PLAN.md. No issue tracker was read today.
- No code changed. No file outside `AUTOPILOT/` changed.

**Tests**

- `uv run pytest -q` in the cloud run (Python 3.13.18; CI uses 3.11): 9 passed.
- `uv run ruff check .`: all checks passed. `uv run ruff format --check .`: 8 files already
  formatted.
- `go test ./...` in the cloud run: could not run, see the notice above.
- GitHub Actions run 45887071833 on `autopilot` at 82ce8d4 (the same commit as `main`): both jobs
  succeeded, `go` (vet, gofmt, 18 tests) and `python` (ruff, pytest).

**Next slice**

- Slice 1, due Nov 27, 2026: mock server with `/v1/models` and plain `/v1/completions`.

**Armaan must do**

- Nothing now. The first entry in `RUN_THESE.md` is expected with slice 15.
- Optional: decide whether the cloud run should be allowed to download the Go toolchain (see the
  notice above).
- Optional: read the "Design choices" part of PLAN.md. The one choice worth a second look is that
  all new code is Python and the Go load generator is left unchanged.

## Nov 26, 2026, second run: plan revision and slice 1 (mock server, plain completions)

This was the second run on Nov 26. It did the one-time plan revision the updated task asks for,
then slice 1. Slice 1 is therefore one day ahead of the first plan.

**Actions result of the last push**

- Run 45887693451, workflow `test`, on `autopilot` at a6d63a1: concluded success.

**Plan revision (commit 6b1e6d0)**

- PLAN.md has a new section "GPU runs": one trigger (a push to `autopilot` that changes a file
  under `runs/requests/`), the three allowed actions, a fixed time limit on every Modal function
  and on the job, the budget check before launch, the ledger `results/SPEND.md`, one request per
  day, smallest run first.
- A new Part B (slices 7, 8, 10, 11, 12) builds the ledger, the budget check, the run driver and
  the workflow file, then sends a smoke request with no GPU.
- The slices that waited for Armaan's result files (W1 to W4) are folded into numbered slices
  23, 28, 33 and 36. The slices that added RUN_THESE.md entries now push request files (slices
  13, 22 and 29). The old to new numbering is at the end of PLAN.md.
- The plan is stricter than the task in one place: a request is refused when its worst case (its
  full time limit at the listed prices) plus the ledger total would pass 100 dollars, not only
  when its estimate would.
- RUN_THESE.md now holds only what the workflow cannot do. It has no entries. UPSTREAM.md notes
  that a reproduction can be run by the workflow.
- Price check: on Nov 26, 2026 https://modal.com/pricing listed L4 at 0.000222 dollars per
  second, CPU at 0.0000131 dollars per core per second and memory at 0.00000222 dollars per GiB
  per second. These are the constants already in `bench/matrix.py`. No constant was changed.
- Planned spend in PLAN.md is under 10 dollars in total. Every figure there is an estimate from
  `matrix.estimate`, not a measurement.

**Slice 1 done**

- `bench/mock_server.py`: `GET /v1/models` and `POST /v1/completions` without streaming, on the
  standard library HTTP server, bound to 127.0.0.1. Each output token is a pure function of
  (prompt, seed, position). `usage` is returned, and `max_tokens` is honoured. Streaming and
  prompt lists are refused with HTTP 400 until slices 3 and 5 add them, so a client cannot pass a
  test by getting an answer in the wrong shape.
- `python bench/mock_server.py --port 8000` starts it by hand. `make mock` comes with slice 6.
- No other file changed. No dependency was added, `uv.lock` is unchanged.

**Tests**

- Test first: `tests/test_mock_server.py` failed at import (no module `mock_server`), then passed.
- `uv run pytest -q` in the cloud run (Python 3.13.18): 30 passed (9 old, 21 new).
- The same suite under Python 3.11, the version CI uses: 30 passed.
- `uv run ruff check .`: all checks passed. `uv run ruff format --check .`: 14 files already
  formatted.
- `go test ./...` in the cloud run: could not run, see the first notice. No Go code changed. CI
  covers it, and the next run reads the result.

**Next slice**

- Slice 2, Scout 1: both contribution guides, vLLM issue 27433, SGLang issue 10278, and whether
  the pinned engine versions have the deterministic modes.

**Armaan must do**

- Nothing is required.
- Worth knowing: the plan is now 37 slices and ends Jan 1, 2027 with no lost days.
- Worth knowing: the existing `.github/workflows/test.yml` uses the action `astral-sh/setup-uv`
  and also runs on `pull_request`. It was left unchanged, because it is Armaan's file and it uses
  no secrets. The workflow files the autopilot writes will use only `actions/checkout`,
  `actions/setup-python` and `actions/setup-go`, and no pull request trigger. Say so if `test.yml`
  should be changed to match.
- Worth knowing: the GPU workflow will ask for write permission to repository contents so it can
  commit result files to `autopilot`. If a repository rule blocks that, the smoke request of
  slice 12 will show it and the log will say so.
