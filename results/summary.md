| Engine | Prefix cache | Bucket | Concurrency | Output tok/s | TTFT p50 ms | TTFT p95 ms | TTFT p99 ms | Latency p95 ms | $/1M output tokens |
|---|---|---|---|---|---|---|---|---|---|
| sglang | on | long | 1 | 17.2 | 122 | 322 | 322 | 7564 | $12.94 |
| sglang | on | long | 8 | 112.4 | 1196 | 1874 | 1875 | 9566 | $1.97 |
| sglang | on | long | 32 | 310.2 | 449 | 6748 | 7276 | 16708 | $0.72 |
| sglang | on | medium | 1 | 17.5 | 121 | 157 | 157 | 7347 | $12.71 |
| sglang | on | medium | 8 | 129.5 | 538 | 544 | 544 | 8013 | $1.71 |
| sglang | on | medium | 32 | 422.9 | 283 | 1933 | 1934 | 10484 | $0.52 |
| sglang | on | short | 1 | 17.5 | 120 | 129 | 129 | 7316 | $12.68 |
| sglang | on | short | 8 | 134.4 | 216 | 217 | 217 | 7643 | $1.65 |
| sglang | on | short | 32 | 449.0 | 258 | 805 | 814 | 9188 | $0.49 |
| vllm | off | long | 32 | 147.1 | 2386 | 17113 | 18640 | 41901 | $1.51 |
| vllm | off | medium | 32 | 312.3 | 1680 | 4585 | 4591 | 15722 | $0.71 |
| vllm | off | short | 32 | 427.6 | 809 | 1327 | 1331 | 9643 | $0.52 |
| vllm | on | long | 1 | 17.2 | 83 | 282 | 282 | 7535 | $12.89 |
| vllm | on | long | 8 | 112.2 | 1020 | 1948 | 1948 | 10044 | $1.98 |
| vllm | on | long | 32 | 252.7 | 2318 | 6245 | 6670 | 20219 | $0.88 |
| vllm | on | medium | 1 | 17.6 | 83 | 100 | 100 | 7305 | $12.65 |
| vllm | on | medium | 8 | 128.6 | 478 | 583 | 583 | 8074 | $1.73 |
| vllm | on | medium | 32 | 394.7 | 1328 | 1842 | 1886 | 10531 | $0.56 |
| vllm | on | short | 1 | 17.6 | 72 | 80 | 80 | 7274 | $12.60 |
| vllm | on | short | 8 | 133.4 | 274 | 280 | 280 | 7729 | $1.66 |
| vllm | on | short | 32 | 459.3 | 639 | 662 | 662 | 8918 | $0.48 |

Model Qwen/Qwen2.5-7B-Instruct, dtype bfloat16, GPU L4, max_tokens 128. Cells measured between 2026-09-22T20:04:40Z and 2026-09-23T00:46:46Z at commits 33da131, 43f2595, 807dcc4. Each cell's own commit and timestamp are in its JSON file.

## Cold start

Time from launching the server process to the first healthy response, then the discarded warm-up pass. Neither is in the measurements above.

| Engine | Prefix cache | Server ready (s) | Warm-up (s) |
|---|---|---|---|
| sglang | on | 122 | 76 |
| vllm | on | 149 | 49 |
| vllm | off | 85 | 51 |

## Environment

**sglang 0.5.2, prefix caching on**

- GPU: NVIDIA L4, driver 580.95.05, 23034 MiB
- Base image: nvidia/cuda:12.8.1-devel-ubuntu22.04
- torch 2.8.0, dtype bfloat16, max model len 4096, gpu memory fraction 0.9
- Model: Qwen/Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28
- Server flags: `-m sglang.launch_server --model-path Qwen/Qwen2.5-7B-Instruct --dtype bfloat16 --port 8000 --context-length 4096 --mem-fraction-static 0.9`

**vllm 0.20.2, prefix caching on**

- GPU: NVIDIA L4, driver 580.95.05, 23034 MiB
- Base image: debian_slim (prebuilt kernels)
- torch 2.11.0, dtype bfloat16, max model len 4096, gpu memory fraction 0.9
- Model: Qwen/Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28
- Server flags: `-m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-7B-Instruct --dtype bfloat16 --port 8000 --max-model-len 4096 --gpu-memory-utilization 0.9`

**vllm 0.20.2, prefix caching off**

- GPU: NVIDIA L4, driver 580.95.05, 23034 MiB
- Base image: debian_slim (prebuilt kernels)
- torch 2.11.0, dtype bfloat16, max model len 4096, gpu memory fraction 0.9
- Model: Qwen/Qwen2.5-7B-Instruct revision a09a35458c702b33eeacc393d103063234e8bc28
- Server flags: `-m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-7B-Instruct --dtype bfloat16 --port 8000 --max-model-len 4096 --gpu-memory-utilization 0.9 --no-enable-prefix-caching`
