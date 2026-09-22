# Architecture

## Pieces

| Path | Does |
|---|---|
| `cmd/loadgen` | CLI: flags to one `loadgen.Config`, runs one cell, prints the summary |
| `internal/openai` | streaming `/v1/completions` client and SSE parser, measures TTFT and total time |
| `internal/loadgen` | prompt buckets, the closed-loop worker pool, JSONL and summary writers |
| `internal/stats` | nearest-rank percentiles and the per-cell summary |
| `bench/matrix.py` | the 21 cells, per-cell GPU-second estimate, cost estimate |
| `bench/modal_app.py` | Modal images, engine startup, one container per engine configuration |
| `bench/report.py` | `results/summary.md` and the tokens-per-second chart |

## One cell

A cell is one engine, one concurrency, one prompt bucket. The loadgen starts `concurrency` workers, each holding exactly one request in flight, drains a warmup queue that is not recorded, then drains `requests` measured jobs while the wall clock runs. Aggregate throughput is measured output tokens over that wall time, so queueing counts against the engine.

Per request it records TTFT, end-to-end latency, the prompt tokens the engine reports, and the completion tokens the engine reports. A request that streams no text, or that comes back without usage accounting, is recorded as an error rather than guessed at. A cell where every request failed returns an error instead of a summary.

## Prompt buckets

Each bucket has a target length: short 128 tokens, medium 512, long 2048. A prompt is 60% shared prefix, seeded per bucket, and 40% unique tail, seeded per request index. The shared part gives prefix caching something to reuse; the unique part stops the whole request being served from cache. Words come from a fixed vocabulary of common short words, which cost close to one token each, and the achieved `prompt_tokens` is written into every record so the real length is in the data.

## Decisions

- Chose client-side TTFT over server-log TTFT because queueing delay is invisible in server logs and is exactly what continuous batching changes.
- Chose a warmup phase over a cold first request because CUDA graph capture and allocator growth otherwise land in the p99.
- Chose one GPU class (L4) over a spread of GPUs because two variables in one table answer no question.
- Chose cost per million output tokens over cost per hour because the per-hour rate is identical for both engines and hides the difference.
- Chose `/v1/completions` over `/v1/chat/completions` because a raw prompt avoids two different chat templates changing the token count.
- Chose `ignore_eos` with a fixed `max_tokens` over natural stopping because a model that stops early otherwise looks faster.
- Chose the server's `completion_tokens` over counting streamed chunks because a chunk can carry several tokens.
- Chose Qwen2.5-7B-Instruct over Llama-3.1-8B-Instruct because Llama is gated on Hugging Face and a gated model blocks reproduction.
- Chose a Go load generator over a Python one because the client should not become the bottleneck it is trying to measure.
- Chose nearest-rank percentiles over interpolation so every reported percentile is a request that actually happened.
- Chose a prebuilt linux/amd64 binary over installing Go in the engine image because the image already carries a large CUDA stack.
- Chose one container per engine configuration over one per cell because model load costs about three minutes and would otherwise dominate the bill.
- Chose an explicit `--confirm` flag over a bare `modal run` because the default outcome of a mistake should be printing the plan, not spending money.

## What this does not control for

Engine version (pinned, but a release can move the numbers), kernel and driver version inside the Modal image, the specific L4 the scheduler hands out, and background load on that host. Both engines run in the same image family and the same GPU class, which removes most of it, but a rerun on another day can differ.

## What I would change

- Add open-loop arrivals at a fixed request rate, since closed-loop concurrency hides what happens past saturation.
- Record inter-token latency, not just TTFT and total time.
- Repeat each cell three times and report the spread.
- Add a quality check on the outputs so a fast engine returning short or degenerate text cannot look good.
