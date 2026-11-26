# Inference gate: run log

One entry per run, oldest first. Notices that Armaan must see go in the section right below.

## Notices

- **Nov 26, 2026. Go tests cannot run in the cloud run.** `go.mod` asks for Go 1.27.1, the cloud
  run has Go 1.24.7, and the session's network policy refuses the toolchain download (host
  `proxy.golang.org`). This was not worked around. The plan changes no Go code, and GitHub Actions
  runs the Go job on every push to `autopilot`, so each run reads the Actions result and records
  it here. No action is needed for the plan as written. If the cloud run should run Go tests
  itself, allow the Go toolchain download for this environment.

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
