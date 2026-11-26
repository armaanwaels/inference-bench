# Inference gate: plan

Written Nov 26, 2026 by the first autopilot run, from commit 82ce8d4 on `main`.
Revised once, later on Nov 26, 2026, after Armaan added automated GPU runs to the task. The
revision is described in "What changed in the Nov 26 revision" at the end of this file.

One slice per daily run. Slice 1 was done on Nov 26, 2026. With no lost days slice N lands on
Nov 25 plus N days, so slice 37 lands on Jan 1, 2027, inside the allowed window (not before
Dec 16, 2026, not after Jan 25, 2027). Every lost day moves the end date by one day.

## Where the repository stood on Nov 26, 2026

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
- **GPU steps run through one GitHub Actions workflow, started by a request file.** See "GPU runs"
  below. The autopilot never holds a token. It writes a request file, the workflow runs it on
  Modal and commits the result files, and the next day's run reads the outcome.
- **Order: mock, GPU workflow, first repeated run, correctness, intervals, gate.** The workflow
  comes right after the mock so that real result files arrive while the analysis code is being
  written. The first repeated run comes before the correctness suite because it needs almost no
  new code. The correctness suite still comes before the interval code, because upstream
  reproduction steps (due by Dec 17) are written as commands of the correctness suite.
- **New result files go in new directories** (`results/repeats/`, `results/correctness/`,
  `results/candidate/`). The existing 21 single-run files and their table stay as they are,
  labelled "one run per cell".

## GPU runs

This section is the contract for every slice that touches the workflow. The cloud run itself has
no GPU and no tokens, and that does not change.

**How a run starts.** The autopilot commits one new file `runs/requests/<date>-<name>.json` to
`autopilot`. The workflow `.github/workflows/gpu-run.yml` has exactly one trigger: a push to the
branch `autopilot` that changes a file under `runs/requests/`. It has no schedule, no manual
trigger, no `pull_request` and no `pull_request_target` trigger. One request file is one run. A
request file is never edited after it is pushed; a second try is a new file on a later day.

**What the workflow may use.** Only `actions/checkout`, `actions/setup-python` and
`actions/setup-go`. Python packages are installed with `pip`. The Modal token reaches the one step
that calls Modal through the repository secrets `MODAL_TOKEN_ID` and `MODAL_TOKEN_SECRET`, as
environment variables of that step only. No step prints the environment, turns on shell tracing,
or echoes a secret. The autopilot never sees, types or asks for a token.

**Hard limits on time.** Every Modal function the workflow calls has a fixed `timeout`. The
workflow job has `timeout-minutes`. A request names its own limit, and the run driver refuses a
request whose limit is above 60 GPU minutes.

**Budget.** Total spend for this project stays under 100 US dollars. Before anything is launched
the run driver:

1. Estimates the cost of the request from the price Modal lists. The prices live in
   `bench/matrix.py` with the date they were read. On Nov 26, 2026 the page
   https://modal.com/pricing listed L4 at 0.000222 dollars per second, CPU at 0.0000131 dollars
   per core per second and memory at 0.00000222 dollars per GiB per second. These match the
   constants in `matrix.py`, which were read on Sep 22, 2026.
2. Works out the worst case: the request's time limit priced at the same rates. One L4 container
   as configured (4 cores, 32 GiB) is about 1.24 dollars an hour at those prices, so a request at
   the 60 minute cap cannot cost more than about 1.24 dollars.
3. Reads the running total from `results/SPEND.md`.
4. Aborts if the estimate plus the running total would pass 100 dollars. This plan is stricter
   than the task asks: it also aborts if the worst case plus the running total would pass 100.

After the run the workflow appends one row to `results/SPEND.md`: the request, the measured GPU
minutes, and the cost at the listed prices. The cost counts the GPU and the CPU and memory of the
same container. A run that failed, or whose time could not be measured, is charged at its full
time limit. If a workflow run ends without a row (for example the job was cancelled), the next
day's cloud run adds the row at the full time limit. The ledger is measured time multiplied by
listed prices. The real invoice is on Modal's side, and Armaan can compare the two at any time.

**One request per day.** At most one request file per calendar day (UTC). The run driver refuses
a request when another request has the same date, and when the date in the file name is not the
day of the push.

**Smallest run first.** The first request is a smoke check with no GPU. The first GPU request is
one pass of the existing matrix. Larger requests come only after a smaller one was read and found
sound.

**A request is pushed only when things are green.** The Python tests passed in the cloud run for
that commit, and the Actions result of the previous push was green.

**Planned requests.** Estimates come from `bench/matrix.py` (`estimate`), not from measurements.
The 21 cells of one pass are estimated at 26.3 GPU minutes and 0.55 dollars.

| Request | Pushed with slice | What it answers | Estimate |
|---|---|---|---|
| smoke | 12 | Does the workflow build, reach Modal, commit files and write the ledger | no GPU, about a cent of CPU |
| repeats r01 | 13 | Does a repeated pass work end to end, and how far does a second pass move | 0.55 dollars |
| repeats r02, r03, r04, r05 | 14, 16, 17, 18 | More passes for the intervals, one pass per request | 0.55 dollars each |
| correctness, vLLM | 22 | Does output change with batch size, in default and batch-invariant mode | set in slice 20, at most 1.24 dollars |
| correctness, SGLang | 23 | The same for SGLang, default and deterministic mode | set in slice 20, at most 1.24 dollars |
| candidate c01 to c03 | 29 to 31 | A run set on a newer engine release, for the gate | about 0.55 dollars a pass |

One pass per request keeps every request well under the 60 minute cap. Planned total: under
10 dollars. A reproduction of an upstream issue may add one or two small
requests. Nothing in this plan needs more than 25 dollars, so the 100 dollar limit is far away,
and the checks above hold it even if a plan is wrong.

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
- Slices 6 and 35 add tests that need a built load generator. Those tests skip where Go cannot
  build and run in CI. Their real result is the CI result, read by the next run.
- The GPU workflow builds the load generator itself with `actions/setup-go`, so GPU runs do not
  depend on Go in the cloud run either.

If Armaan wants the cloud run to run Go tests itself, the fix is on his side (allow the Go
toolchain download for this environment). Nothing in the plan depends on it.

## Standing rules for every run

1. Read the GitHub Actions results for the last push to `autopilot`: the test workflow, and the
   GPU workflow if a request was pushed. Record both in LOG.md. If the test workflow is red,
   fixing it is today's slice, and the planned slice moves one day. If a GPU run failed, record
   why, make sure `results/SPEND.md` has its row, and fix the cause before any new request.
2. Test first. See the new test fail, then make it pass.
3. Before the commit run `uv run pytest -q`, `uv run ruff check .` and
   `uv run ruff format --check .`. Record the counts in LOG.md. Record that Go tests are covered by
   CI only.
4. Tests use `127.0.0.1` and an ephemeral port only. No test may need a GPU, a key or the network.
5. No result number is written anywhere unless it comes from a result file committed in this
   repository. Test fixtures with made-up numbers live under `tests/` and are named as fixtures.
   They never go in `results/`.
6. Old numbers in the README keep the "one run per cell" caveat.
7. GPU steps go through the workflow, under the rules in "GPU runs". Anything that cannot be done
   through the workflow becomes an entry in `AUTOPILOT/RUN_THESE.md` with exact commands and the
   expected output files.
8. From Dec 17, 2026: if `UPSTREAM.md` has no issue with a reproduction, say so at the top of
   LOG.md.
9. If a slice turns out too big for a 15 minute review, do the first half, split the slice in this
   file, and log the change. The plan may be edited, and every edit is logged.
10. Push only to `autopilot`. No em dashes.
11. A slice that waits for result files which have not arrived does its code part, logs
    "waiting for result files" in one line, and the report part moves to the next run.

## Slices

Status key: `[ ]` not started, `[x]` done (with date). "Scout" slices only read and write notes.
"Request" means the slice also commits one request file, under the rules in "GPU runs".

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
  when Go cannot build. A new CI job with both Go and Python runs it, using only
  `actions/checkout`, `actions/setup-go` and `actions/setup-python`. `make mock` starts the mock
  by hand. Result confirmed from the CI run by the next slice.

### Part B: GPU run workflow (added in the Nov 26 revision)

- [ ] **7. Spend ledger.** `bench/spend.py`: the format of `results/SPEND.md` (one table row per
  run: date, request, outcome, GPU minutes, cost, running total), a parser, the running total, and
  an append that never rewrites old rows. A run with an unknown or failed outcome is charged at
  its full time limit. Creates `results/SPEND.md` with a zero total. Test: round trip, total,
  a damaged file is an error and never read as zero, the worst case rule.
- [ ] **8. Request file and budget check.** `bench/gpu_request.py`: the request format
  (`runs/requests/<date>-<name>.json`: kind, selection, repeats, time limit, the question it
  answers), validation, the cost estimate from `matrix.estimate` and the listed prices, the worst
  case from the time limit, and the decision: go, or abort with a reason. Aborts when the estimate
  or the worst case plus the ledger total would pass 100 dollars, when the limit is above
  60 minutes, when the date is not today (UTC), and when another request has the same date.
  Test: each abort reason, the boundary at exactly 100, and a request that passes.
- [ ] **9. Scout 2.** Search both trackers for open issues about batch-dependent output,
  determinism at temperature 0, seeds, prefix cache and output differences, and usage or token
  accounting in streaming. For each candidate write reproduction steps.
- [ ] **10. Run driver.** `bench/gpu_run.py`: the one command the workflow calls. It finds the
  request file changed by the push (exactly one, or it stops), runs the budget check, builds the
  Modal command for the request kind, runs it under the time limit, moves result files to their
  directory, and appends the ledger row whatever the outcome. `modal_app.py` gets fixed timeouts
  that match the request limit. Test: with a fake runner in place of Modal, so nothing is
  launched: the command per kind, the ledger row on success, on failure and on timeout, and a
  refusal when two request files change in one push.
- [ ] **11. Workflow file.** `.github/workflows/gpu-run.yml` as described in "GPU runs". The job
  has `timeout-minutes`, write permission for repository contents only, and a concurrency group
  so two runs never overlap. It commits only files under `results/` and pushes to `autopilot`.
  No request file is pushed in this slice, so the workflow does not start. Test: a pytest reads
  the workflow text and fails on a schedule, manual, `pull_request` or `pull_request_target`
  trigger, on any action outside the three allowed, on a missing time limit, on shell tracing or
  an environment dump, and on a secret used outside the Modal step. The next run confirms from
  the Actions list that this push did not start the workflow.
- [ ] **12. Request: smoke check, no GPU.** The first request runs the existing `smoke` entry
  point (image checks on CPU). It proves the build, the secrets, the commit back to `autopilot`
  and the ledger row before any GPU time is bought. The next run reads the result. If the
  workflow cannot reach Modal or cannot push, that goes to LOG.md as a step for Armaan.

### Part C: first repeated run (goal 1)

- [ ] **13. Repeats in the matrix and the Modal app. Request: repeats r01.** `--repeats N` in
  `matrix.py` with the cost estimate scaled, and a loop in `modal_app.py` that writes each repeat
  to `results/repeats/rNN/` and pulls nested directories back. Per-request records of repeats are
  kept (the ignore rule only covers the top level of `results/`). Test: estimate, directory
  names, argument lists. The request is one pass of the 21 cells.

### Part D: correctness suite (goal 2)

- [ ] **14. Prompt set and stream hashing. Request: repeats r02, if r01 was sound.** A
  committed prompt file (`bench/prompts/correctness_v1.jsonl`) with short, medium and long
  prompts, and its SHA-256 recorded in every result. `bench/correctness.py`: hash of a token
  list, hash of text, and the first position where two streams differ. Test: known vectors, order
  matters, empty stream is handled.
- [ ] **15. Scout 3.** Follow up on candidates: check whether each still reproduces on current
  releases according to the thread, whether someone is assigned, and what a maintainer asked for.
  Drop stale ones. Mark the two best.
- [ ] **16. Correctness client: reference pass. Request: repeats r03.** Send every prompt
  alone (batch size 1, one request in flight), record tokens, hashes and the request settings.
  Define the result file format. Test against the mock: every prompt has a record, and a failed
  request is recorded as a failure, never as a match.
- [ ] **17. Conditions and comparison. Request: repeats r04.** Run the same prompts at batch sizes
  1, 4 and 16 and at 1, 8 and 32 requests in flight. Compare every output with the reference.
  Report mismatches per condition with the first differing position. Test: the clean mock gives
  zero mismatches, the mock with the batch fault is caught, and the report names the right
  condition and position.
- [ ] **18. Order and background traffic. Request: repeats r05.** Shuffle prompt order with a
  recorded seed and add background requests of other lengths, so the batch around a prompt changes.
  Run the reference pass twice, to tell "differs from run to run even alone" apart from "differs
  with batching". Test: both cases are told apart on scripted mock faults.
- [ ] **19. Sampling settings.** Two profiles: greedy (temperature 0) and seeded sampling
  (temperature above 0 with a fixed seed). The exact request fields per engine come from the docs
  read in the scout slices. The profile is part of every record and of the hash input description.
  Test: the mock honours the seed, same seed matches, different seeds differ.
- [ ] **20. Engine modes.** Server commands and environment for each engine in default mode and
  in deterministic mode (`VLLM_BATCH_INVARIANT=1`; `--enable-deterministic-inference` with a
  supported attention backend). Correctness cells added to `matrix.py` with their own time and
  cost estimate. Test: pure functions only (commands, environment, cell list, estimate).
- [ ] **21. Scout 4.** Rewrite the reproduction steps of the best candidates as commands of this
  repository's correctness suite, so the workflow can run them. Check the Dec 17 rule early.
- [ ] **22. Modal entry point for correctness. Request: correctness, vLLM.** An entry point that
  starts an engine in each mode, runs the correctness client next to it and writes
  `results/correctness/<engine>-<mode>.json`. Nothing launches without `--confirm`. The run
  driver learns the request kind. Test: argument building and file naming. The request covers
  vLLM in default and batch-invariant mode.
- [ ] **23. Correctness section of the report. Request: correctness, SGLang.** `report.py` adds a
  correctness section from the files in `results/correctness/`: mismatches per engine, mode and
  condition. With no files the output is unchanged. Test: fixtures. The real section is generated
  from the vLLM files if they have arrived, and again when the SGLang files arrive.

### Part E: confidence intervals (goal 1)

- [ ] **24. Bootstrap core.** `bench/bootstrap.py`: percentile bootstrap interval for a statistic,
  with a seed so the same input gives the same interval. Test: constant sample gives zero width,
  same seed repeats, interval contains the sample statistic, a wider sample gives a wider
  interval, too few values is an error and not an interval.
- [ ] **25. Run sets.** `bench/runs.py` reads `results/repeats/rNN/` (summary plus per-request
  records), groups by cell, and refuses to mix runs that differ in model, dtype, GPU, engine
  version, flags or `max_tokens`. Missing cells are listed. Test: synthetic fixture run sets under
  `tests/`, then one check that the committed repeats load.
- [ ] **26. Intervals for request metrics.** Throughput: interval over runs. TTFT and latency
  percentiles: resample runs, then requests inside each run. The percentile is nearest rank, the
  same rule as `internal/stats`. Test: a shared table of inputs and expected percentiles copied
  from the Go tests, and interval properties on fixtures.
- [ ] **27. Scout 5.** Read recent merged pull requests in the area of the best candidate, to
  learn what tests and benchmarks maintainers asked for. Note this for Armaan's patch.
- [ ] **28. Report with intervals.** `report.py` adds a table with intervals when a run set
  exists, and error bars on the chart. The single-run table stays and is labelled one run per
  cell. With no run set the output is unchanged. Test: fixtures; the existing report tests still
  pass. Then the report is regenerated from the committed repeats, and the README gains a table
  whose every number comes from those files.

### Part F: release gate (goal 3)

- [ ] **29. Candidate engine versions. Request: candidate c01.** Engine versions can be
  overridden for a candidate run and are recorded in every result. Results go to
  `results/candidate/<name>/rNN/`. Test: version plumbing as pure functions. The request is one
  pass on a newer engine release. Requests c02 and c03 follow with slices 30 and 31 if c01 was
  sound.
- [ ] **30. Gate policy file.** `gate.toml`: threshold per metric (throughput drop, TTFT and
  latency rise), confidence level, minimum repeats, and which engine modes must match exactly.
  Parser with clear errors. Test: good file, unknown key, missing threshold, bad value.
- [ ] **31. Performance verdicts.** Compare a baseline run set with a candidate run set, cell by
  cell. Bootstrap interval of the ratio. Verdict per metric: pass, fail (the whole interval is
  beyond the threshold), or inconclusive (the estimate is beyond it but the interval is not).
  Test: fixtures for each verdict, and identical run sets always pass.
- [ ] **32. Correctness verdicts.** Read correctness results. Fail on any mismatch in a mode the
  policy says must be exact. Fail when a required result file is missing or has failed requests.
  Mismatches in default mode are reported as a rate. Test: each case on fixtures.
- [ ] **33. Scout 6.** Final shortlist in `UPSTREAM.md`: ranked, each with link, status and date
  seen, why it fits, reproduction steps, what the workflow runs showed (with the result file
  paths), and what a patch would need. Recommend one to Armaan.
- [ ] **34. Gate command.** `python bench/gate.py --baseline DIR --candidate DIR --correctness DIR
  --policy gate.toml`. Exit 0 pass, 1 performance regression, 2 correctness failure, 3 bad input.
  A flag makes inconclusive count as failure. Writes a markdown and a JSON report. `make gate`.
  Test: exit codes through a subprocess.
- [ ] **35. Gate demo on the mock.** Three scripted mocks: healthy, slow, batch-dependent. The
  gate exits 0, 1 and 2. The correctness path runs everywhere; the performance path needs the Go
  load generator, so it runs in CI and skips in the cloud run. `make gate-demo`.
- [ ] **36. Gate on the real run sets.** Run the gate with the committed repeats as baseline, the
  committed candidate run set and the committed correctness results. Commit its report under
  `results/gate/` and describe the verdict, with the exit code, in LOG.md.
- [ ] **37. Documentation and handoff.** README and ARCHITECTURE describe the mock, the GPU
  workflow and its budget rules, the correctness suite, repeats and the gate. Numbers only from
  committed result files. Old numbers keep the caveat. `RUN_THESE.md` and `results/SPEND.md`
  reviewed top to bottom. LOG.md gets a closing summary with the total spend.

## What Armaan must do

1. Nothing while he is away, as long as the workflow can reach Modal and push. If it cannot (a
   secret is missing or expired, or Actions is not allowed to push to `autopilot`), LOG.md says so
   at the top and GPU slices wait.
2. Review `autopilot` and merge it by hand when a batch looks right.
3. Choose the upstream issue from `UPSTREAM.md`, then write and submit the patch himself.
4. Optional: compare `results/SPEND.md` with the Modal billing page now and then.
5. Pause or delete the scheduled task when the plan is done, at the latest Jan 25, 2027.

## What changed in the Nov 26 revision

The first plan had 30 slices and assumed no GPU result could arrive before Jan 5, 2027: GPU steps
were commands for Armaan in `RUN_THESE.md`, and four slices (W1 to W4) waited for his result
files. The task now allows GPU runs through a GitHub Actions workflow, so:

- A new Part B (slices 7, 8, 10, 11 and 12) builds the workflow, the budget check and the spend
  ledger. The section "GPU runs" holds the rules.
- The old slice 20 (repeats in the matrix and the Modal app) moved forward to slice 13, so the
  first repeated pass runs early.
- The old waiting slices are folded into numbered slices: W1 into slice 28, W2 into slice 23, W3
  into slice 36, W4 into slice 33.
- The old slices 15, 20 and 29, which added `RUN_THESE.md` entries, now push request files
  instead (slices 22, 13 and 29).
- Renumbering, old to new: 1 to 6 unchanged, 7 to 9, 8 to 14, 9 to 16, 10 to 17, 11 to 18,
  12 to 15, 13 to 19, 14 to 20, 15 to 22, 16 to 24, 17 to 21, 18 to 25, 19 to 26, 20 to 13,
  21 to 28, 22 to 27, 23 to 30, 24 to 31, 25 to 32, 26 to 34, 27 to 33, 28 to 35, 29 to 29,
  30 to 37.
- The plan grew from 30 to 37 slices and the end date moved from Dec 26, 2026 to Jan 1, 2027,
  still inside the window.
