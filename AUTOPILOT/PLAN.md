# Inference gate: plan

Written Nov 26, 2026 by the first autopilot run, from commit 82ce8d4 on `main`.
One slice per daily run. Slice 1 is due Nov 27, 2026. With no lost days slice 30 lands on
Dec 26, 2026, inside the allowed window (not before Dec 16, 2026, not after Jan 25, 2027).
Every lost day moves the end date by one day.

## Where the repository stands today

- A Go load generator (`cmd/loadgen`, `internal/`) drives one cell: one engine, one concurrency,
  one prompt bucket. It records TTFT, latency and token counts per request. It does not keep the
  generated text.
- `bench/matrix.py` defines 21 cells. `bench/modal_app.py` runs them on one L4 on Modal.
  `bench/report.py` writes `results/summary.md` and one chart.
- `results/` holds one summary file per cell, so one run per cell. The per-request `.jsonl`
  files were never committed (`.gitignore` excludes `results/*.jsonl`).
- Pinned engines: vllm 0.20.2 and sglang 0.5.2.
- Tests: 18 Go tests and 9 Python tests. CI runs `go vet`, `gofmt`, `go test`, `ruff` and `pytest`
  on every push to any branch.

## Goal

Turn the benchmark into a correctness and performance gate:

1. Repeated runs per cell with bootstrap confidence intervals.
2. A correctness suite: same prompts and sampling settings across batch sizes and concurrency
   levels, output token streams hashed and compared, including each engine's deterministic or
   batch-invariant mode.
3. A release-gate command that exits non-zero on a correctness failure or on a latency or
   throughput regression beyond a stated threshold.
4. A scripted mock inference server, so every test runs on CPU with no GPU and no network.
5. A shortlist of open upstream issues in vLLM and SGLang that this work could help with.

## Design choices made in this plan

- **All new code is Python in `bench/`, standard library only.** The gate is analysis and
  orchestration, which is where `report.py` and `matrix.py` already live. No new dependency means
  `uv.lock` does not change.
- **The Go load generator is not changed.** It stays the timing client. Repeated runs are done by
  calling it several times with a different `-out` directory, which needs no Go change.
  There is also a practical reason, see "Go in the cloud run" below.
- **The correctness client is separate from the timing client.** Hashing output in the timing path
  would add client work to the thing being timed. The correctness client is a small Python program
  that runs next to the engine, the same way the load generator does.
- **The mock server is the test double for both clients.** It speaks the same `/v1/completions`
  wire format the Go client parses, and it can be scripted to be slow, to fail, or to give
  batch-dependent output, so each gate verdict can be produced on CPU.
- **Order: mock, then correctness, then repeats, then gate.** Correctness comes before repeats
  because upstream reproduction steps (due by Dec 17) are written as commands of the correctness
  suite. No GPU result can arrive before Armaan is back on Jan 5, 2027, so nothing waits on order.
- **New result files go in new directories** (`results/repeats/`, `results/correctness/`). The
  existing 21 single-run files and their table stay as they are, labelled "one run per cell".

## Facts checked on Nov 26, 2026 (to be confirmed against the pinned versions in slice 2)

- vLLM documents a batch-invariant mode enabled with the environment variable
  `VLLM_BATCH_INVARIANT=1`. The page marks it beta, lists Qwen/Qwen2.5-7B-Instruct among tested
  models, requires NVIDIA compute capability 8.0 or higher, and points to tracking issue 27433.
  Source: https://docs.vllm.ai/en/stable/features/batch_invariance/ (the "stable" page, which may
  be newer than the pinned 0.20.2).
- SGLang documents deterministic inference enabled with the server flag
  `--enable-deterministic-inference`, supported with the flashinfer, fa3 and triton attention
  backends. The page says radix cache is not supported with flashinfer in this mode, and points to
  roadmap issue 10278 and a test module `sglang.test.test_deterministic`.
  Source: https://docs.sglang.io/docs/advanced_features/deterministic_inference.md
- Not yet checked: whether sglang 0.5.2 (the pin) already has that flag, and what the vLLM 0.20.2
  page says. Slice 2 checks both. If the pin is too old, the plan gains a note for Armaan, because
  changing an engine pin changes what the old numbers can be compared with.

## Go in the cloud run

`go.mod` asks for Go 1.27.1. The cloud run has Go 1.24.7, and the download of 1.27.1 is refused by
the session's network policy (host `proxy.golang.org`). So `go test ./...` cannot run in the cloud
run. This plan does not work around that. Instead:

- No slice changes Go code, so the Go test result cannot change from slice to slice.
- GitHub Actions runs the Go job (with Go 1.27.1) on every push to `autopilot`. Each run reads the
  Actions result of the previous push first and records it in LOG.md.
- Slices 6 and 28 add tests that need a built load generator. Those tests skip where Go cannot
  build and run in CI. Their real result is the CI result, read by the next run.

If Armaan wants the cloud run to run Go tests itself, the fix is on his side (allow the Go
toolchain download for this environment). Nothing in the plan depends on it.

## Standing rules for every run

1. Read the GitHub Actions result for the last push to `autopilot`. If it is red, fixing it is
   today's slice, and the planned slice moves one day.
2. Test first. See the new test fail, then make it pass.
3. Before the commit run `uv run pytest -q`, `uv run ruff check .` and
   `uv run ruff format --check .`. Record the counts in LOG.md. Record that Go tests are covered by
   CI only.
4. Tests use `127.0.0.1` and an ephemeral port only. No test may need a GPU, a key or the network.
5. No result number is written anywhere unless it comes from a result file committed in this
   repository. Test fixtures with made-up numbers live under `tests/` and are named as fixtures.
   They never go in `results/`.
6. Old numbers in the README keep the "one run per cell" caveat.
7. Anything that needs a GPU or a model API becomes an entry in `AUTOPILOT/RUN_THESE.md` with exact
   commands and the expected output files.
8. From Dec 17, 2026: if `UPSTREAM.md` has no issue with a reproduction, say so at the top of
   LOG.md.
9. If a slice turns out too big for a 15 minute review, do the first half, split the slice in this
   file, and log the change. The plan may be edited, and every edit is logged.
10. Push only to `autopilot`. No em dashes.

## Slices

Status key: `[ ]` not started, `[x]` done (with date). "Scout" slices only read and write notes.

### Part A: scripted mock server (goal 4)

- [ ] **1. Mock server: models and plain completions.** `bench/mock_server.py` on the standard
  library HTTP server. `GET /v1/models`, `POST /v1/completions` without streaming. Output tokens
  are a pure function of (prompt, seed, position), so the same request always gets the same
  tokens. Returns `usage` with prompt and completion token counts. Honours `max_tokens`.
  Test: start on an ephemeral port, same request twice gives identical text, different prompts
  differ, usage adds up, unknown path gives 404.
- [ ] **2. Scout 1.** Read both contribution guides (rules on tests, sign-off, AI-written
  changes). Read vLLM issue 27433 and SGLang issue 10278. Confirm which engine versions have the
  deterministic modes and whether the pins (vllm 0.20.2, sglang 0.5.2) do. Record the first
  candidates in `UPSTREAM.md`.
- [ ] **3. Mock server: streaming.** Server-sent events in the shape `internal/openai/stream.go`
  parses: `data:` frames with `choices[0].text`, a final usage frame when
  `stream_options.include_usage` is set, then `data: [DONE]`. A setting for several tokens per
  chunk. Test: a Python reader that follows the same rules as `ParseLine` gets the same text as the
  non-streaming call, and the usage frame matches.
- [ ] **4. Mock server: script file for timing and faults.** A JSON script sets time to first
  token, time per token, a slowdown factor, and faults: HTTP 500 on chosen requests, a missing
  usage frame, a stream with no text, a stream cut off early. Test: each fault appears exactly
  where the script says, and delays are at least what the script says.
- [ ] **5. Mock server: batches, token lists, seeds, and a batch-dependent fault.** `prompt` as a
  list (one choice per prompt, with `index`), `logprobs` returning the token list, `seed`. One
  scripted fault makes the output change from a chosen token position when the batch size or the
  number of requests in flight passes a limit. This is the defect the correctness suite exists to
  catch. Test: clean mode is identical across batch sizes, fault mode differs from the stated
  position on.
- [ ] **6. Go load generator against the mock, in CI.** A pytest that builds `cmd/loadgen`, runs
  it against the mock and checks the summary (request count, token count, zero errors). It skips
  when Go cannot build. A new CI job with both Go and uv runs it. `make mock` starts the mock by
  hand. Result confirmed from the CI run by the next slice.
- [ ] **7. Scout 2.** Search both trackers for open issues about batch-dependent output,
  determinism at temperature 0, seeds, prefix cache and output differences, and usage or token
  accounting in streaming. For each candidate write reproduction steps.

### Part B: correctness suite (goal 2)

- [ ] **8. Prompt set and stream hashing.** A committed prompt file
  (`bench/prompts/correctness_v1.jsonl`) with short, medium and long prompts, and its SHA-256
  recorded in every result. `bench/correctness.py`: hash of a token list, hash of text, and the
  first position where two streams differ. Test: known vectors, order matters, empty stream is
  handled.
- [ ] **9. Correctness client: reference pass.** Send every prompt alone (batch size 1, one
  request in flight), record tokens, hashes and the request settings. Define the result file
  format. Test against the mock: every prompt has a record, and a failed request is recorded as a
  failure, never as a match.
- [ ] **10. Conditions and comparison.** Run the same prompts at batch sizes 1, 4 and 16 and at
  1, 8 and 32 requests in flight. Compare every output with the reference. Report mismatches per
  condition with the first differing position. Test: the clean mock gives zero mismatches, the
  mock with the batch fault is caught, and the report names the right condition and position.
- [ ] **11. Order and background traffic.** Shuffle prompt order with a recorded seed and add
  background requests of other lengths, so the batch around a prompt changes. Run the reference
  pass twice, to tell "differs from run to run even alone" apart from "differs with batching".
  Test: both cases are told apart on scripted mock faults.
- [ ] **12. Scout 3.** Follow up on candidates: check whether each still reproduces on current
  releases according to the thread, whether someone is assigned, and what a maintainer asked for.
  Drop stale ones. Mark the two best.
- [ ] **13. Sampling settings.** Two profiles: greedy (temperature 0) and seeded sampling
  (temperature above 0 with a fixed seed). The exact request fields per engine come from the docs
  read in the scout slices. The profile is part of every record and of the hash input description.
  Test: the mock honours the seed, same seed matches, different seeds differ.
- [ ] **14. Engine modes.** Server commands and environment for each engine in default mode and
  in deterministic mode (`VLLM_BATCH_INVARIANT=1`; `--enable-deterministic-inference` with a
  supported attention backend). Correctness cells added to `matrix.py` with their own time and
  cost estimate. Test: pure functions only (commands, environment, cell list, estimate).
- [ ] **15. Modal entry point for correctness, and the first RUN_THESE entry.** An entry point that
  starts each engine in each mode, runs the correctness client next to it and writes
  `results/correctness/<engine>-<mode>.json`. Nothing launches without `--confirm`.
  `RUN_THESE.md` gets the exact commands and expected files. Test: argument building and file
  naming.

### Part C: repeated runs and confidence intervals (goal 1)

- [ ] **16. Bootstrap core.** `bench/bootstrap.py`: percentile bootstrap interval for a statistic,
  with a seed so the same input gives the same interval. Test: constant sample gives zero width,
  same seed repeats, interval contains the sample statistic, a wider sample gives a wider
  interval, too few values is an error and not an interval.
- [ ] **17. Scout 4.** Rewrite the reproduction steps of the best candidates as commands of this
  repository's correctness suite, ready for `RUN_THESE.md`. Check the Dec 17 rule early.
- [ ] **18. Run sets.** `bench/runs.py` reads `results/repeats/rNN/` (summary plus per-request
  records), groups by cell, and refuses to mix runs that differ in model, dtype, GPU, engine
  version, flags or `max_tokens`. Missing cells are listed. Test: synthetic fixture run sets under
  `tests/`.
- [ ] **19. Intervals for request metrics.** Throughput: interval over runs. TTFT and latency
  percentiles: resample runs, then requests inside each run. The percentile is nearest rank, the
  same rule as `internal/stats`. Test: a shared table of inputs and expected percentiles copied
  from the Go tests, and interval properties on fixtures.
- [ ] **20. Repeats in the matrix and the Modal app.** `--repeats N` in `matrix.py` with the cost
  estimate scaled, and a loop in `modal_app.py` that writes each repeat to its own directory and
  pulls nested directories back. Per-request records of repeats are kept (the ignore rule only
  covers the top level of `results/`). `RUN_THESE.md` gets the repeated-run commands. Test:
  estimate, directory names, argument lists.
- [ ] **21. Report with intervals.** `report.py` adds a table with intervals when a run set
  exists, and error bars on the chart. The single-run table stays and is labelled one run per
  cell. With no run set the output is unchanged. Test: fixtures; the existing report tests still
  pass.
- [ ] **22. Scout 5.** Read recent merged pull requests in the area of the best candidate, to
  learn what tests and benchmarks maintainers asked for. Note this for Armaan's patch.

### Part D: release gate (goal 3)

- [ ] **23. Gate policy file.** `gate.toml`: threshold per metric (throughput drop, TTFT and
  latency rise), confidence level, minimum repeats, and which engine modes must match exactly.
  Parser with clear errors. Test: good file, unknown key, missing threshold, bad value.
- [ ] **24. Performance verdicts.** Compare a baseline run set with a candidate run set, cell by
  cell. Bootstrap interval of the ratio. Verdict per metric: pass, fail (the whole interval is
  beyond the threshold), or inconclusive (the estimate is beyond it but the interval is not).
  Test: fixtures for each verdict, and identical run sets always pass.
- [ ] **25. Correctness verdicts.** Read correctness results. Fail on any mismatch in a mode the
  policy says must be exact. Fail when a required result file is missing or has failed requests.
  Mismatches in default mode are reported as a rate. Test: each case on fixtures.
- [ ] **26. Gate command.** `python bench/gate.py --baseline DIR --candidate DIR --correctness DIR
  --policy gate.toml`. Exit 0 pass, 1 performance regression, 2 correctness failure, 3 bad input.
  A flag makes inconclusive count as failure. Writes a markdown and a JSON report. `make gate`.
  Test: exit codes through a subprocess.
- [ ] **27. Scout 6.** Final shortlist in `UPSTREAM.md`: ranked, each with link, status and date
  seen, why it fits, reproduction steps, and what a patch would need. Recommend one to Armaan.
- [ ] **28. Gate demo on the mock.** Three scripted mocks: healthy, slow, batch-dependent. The
  gate exits 0, 1 and 2. The correctness path runs everywhere; the performance path needs the Go
  load generator, so it runs in CI and skips in the cloud run. `make gate-demo`.
- [ ] **29. Candidate engine versions.** Engine versions can be overridden for a candidate run and
  are recorded in every result. `RUN_THESE.md` gets the commands for a baseline run set, a
  candidate run set on a newer engine release, and the gate call. Test: version plumbing as pure
  functions.
- [ ] **30. Documentation and handoff.** README and ARCHITECTURE describe the mock, the
  correctness suite, repeats and the gate. No new numbers unless result files were committed by
  then. Old numbers keep the caveat. `RUN_THESE.md` reviewed top to bottom. LOG.md gets a closing
  summary.

### After slice 30: slices that wait for Armaan's result files

A run does one of these only when the files it needs are committed on `autopilot` or `main`. If
none is ready, the run logs "waiting for result files" in one line and stops.

- [ ] **W1.** Repeats committed: regenerate the report with intervals and update the README table
  from those files.
- [ ] **W2.** Correctness results committed: add the correctness section to the report and README.
- [ ] **W3.** Candidate run set committed: run the gate, commit its report, describe the verdict.
- [ ] **W4.** Update `UPSTREAM.md` with what the real runs showed for the chosen issue.

## What Armaan must do, in order

1. Nothing before he is back, unless he wants to. Review `autopilot` and merge it by hand when a
   batch looks right.
2. After slice 15, 20 and 29: run the entries in `RUN_THESE.md` (GPU on Modal) and commit the
   result files.
3. Choose the upstream issue from `UPSTREAM.md`, then write and submit the patch himself.
4. Pause or delete the scheduled task when the plan is done, at the latest Jan 25, 2027.
