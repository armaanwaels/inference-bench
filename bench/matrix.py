"""Run matrix and its cost estimate. Printing it spends nothing."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace

MODEL = "Qwen/Qwen2.5-7B-Instruct"
DTYPE = "bfloat16"
GPU = "L4"
MAX_TOKENS = 128
WARMUP = 4

# Modal published prices, read from modal.com/pricing on 2026-09-22.
GPU_USD_PER_SECOND = {"L4": 0.000222, "A10": 0.000306}
CPU_USD_PER_CORE_SECOND = 0.0000131
MEM_USD_PER_GIB_SECOND = 0.00000222
CONTAINER_CORES = 4
CONTAINER_GIB = 32

# Estimate inputs, not measurements. Single-stream decode on an L4 is bounded by
# memory bandwidth: about 300 GB/s over 15.2 GB of bf16 weights is roughly 19 tokens/s,
# and I assume 15 to leave headroom. Batched throughput saturates well below c x single.
SINGLE_STREAM_TOKENS_PER_S = 15.0
SATURATION_TOKENS_PER_S = 400.0
ENGINE_START_SECONDS = 180

REQUESTS_BY_CONCURRENCY = {1: 8, 8: 32, 32: 64}


@dataclass(frozen=True)
class Cell:
    engine: str
    concurrency: int
    bucket: str
    prefix_caching: bool = True

    @property
    def requests(self) -> int:
        return REQUESTS_BY_CONCURRENCY[self.concurrency]

    @property
    def label(self) -> str:
        suffix = "" if self.prefix_caching else " (prefix caching off)"
        return f"{self.engine} c={self.concurrency} {self.bucket}{suffix}"

    def estimated_seconds(self) -> float:
        tokens = (self.requests + WARMUP) * MAX_TOKENS
        rate = min(self.concurrency * SINGLE_STREAM_TOKENS_PER_S, SATURATION_TOKENS_PER_S)
        return tokens / rate


def matrix() -> list[Cell]:
    cells = [
        Cell(engine, concurrency, bucket)
        for engine in ("vllm", "sglang")
        for concurrency in (1, 8, 32)
        for bucket in ("short", "medium", "long")
    ]
    # Prefix caching is on by default in both engines. This one extra pass turns it off
    # in vLLM at the highest concurrency, which is where a shared prefix pays most.
    cells += [replace(c, prefix_caching=False) for c in cells if c.engine == "vllm" and c.concurrency == 32]
    return cells


def engine_starts(cells: list[Cell]) -> int:
    """Each distinct engine configuration loads the model once."""
    return len({(c.engine, c.prefix_caching) for c in cells})


def estimate(cells: list[Cell]) -> dict[str, float]:
    bench_seconds = sum(c.estimated_seconds() for c in cells)
    total_seconds = bench_seconds + engine_starts(cells) * ENGINE_START_SECONDS
    gpu = total_seconds * GPU_USD_PER_SECOND[GPU]
    cpu = total_seconds * (CONTAINER_CORES * CPU_USD_PER_CORE_SECOND + CONTAINER_GIB * MEM_USD_PER_GIB_SECOND)
    return {
        "bench_seconds": bench_seconds,
        "startup_seconds": engine_starts(cells) * ENGINE_START_SECONDS,
        "total_seconds": total_seconds,
        "gpu_usd": gpu,
        "cpu_and_memory_usd": cpu,
        "total_usd": gpu + cpu,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="print the matrix as JSON")
    args = ap.parse_args()

    cells = matrix()
    est = estimate(cells)
    if args.json:
        import json

        print(json.dumps({"cells": [c.__dict__ for c in cells], "estimate": est}, indent=2))
        return

    print(f"model {MODEL}, dtype {DTYPE}, GPU {GPU}, max_tokens {MAX_TOKENS}, warmup {WARMUP}")
    print(f"{len(cells)} cells, {engine_starts(cells)} engine starts\n")
    print(f"{'cell':<44} {'requests':>9} {'est. seconds':>13}")
    for c in cells:
        print(f"{c.label:<44} {c.requests:>9} {c.estimated_seconds():>13.0f}")
    print(
        f"\nbenchmark {est['bench_seconds'] / 60:.1f} min + startup {est['startup_seconds'] / 60:.1f} min"
        f" = {est['total_seconds'] / 60:.1f} GPU-minutes"
    )
    print(
        f"cost: GPU ${est['gpu_usd']:.2f} + CPU/memory ${est['cpu_and_memory_usd']:.2f}"
        f" = ${est['total_usd']:.2f} at ${GPU_USD_PER_SECOND[GPU]}/s for {GPU}"
    )
    print("Times are estimates. The recorded wall time per cell is in results/.")


if __name__ == "__main__":
    main()
