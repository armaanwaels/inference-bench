"""Turn the per-cell summaries in results/ into a markdown table and one chart."""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
GPU_USD_PER_SECOND = {"L4": 0.000222, "A10": 0.000306}


def load() -> tuple[list[dict], list[dict]]:
    """Cell summaries and cold-start records, kept apart by filename."""
    summaries, cold = [], []
    for path in sorted(RESULTS.glob("*.json")):
        record = json.loads(path.read_text())
        (cold if path.name.startswith("coldstart-") else summaries).append(record)
    if not summaries:
        sys.exit(f"no summaries in {RESULTS}; run `make bench` first")
    return summaries, cold


def cost_per_million_output_tokens(s: dict) -> float | None:
    price = GPU_USD_PER_SECOND.get(s["gpu"])
    if not price or not s["output_tokens_per_s"]:
        return None
    return price / s["output_tokens_per_s"] * 1_000_000


def table(summaries: list[dict]) -> str:
    head = (
        "| Engine | Prefix cache | Bucket | Concurrency | Output tok/s | TTFT p50 ms | TTFT p95 ms |"
        " TTFT p99 ms | Latency p95 ms | $/1M output tokens |"
    )
    rows = [head, "|---|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(summaries, key=lambda x: (x["engine"], x["prefix_caching"], x["bucket"], x["concurrency"])):
        cost = cost_per_million_output_tokens(s)
        rows.append(
            f"| {s['engine']} | {'on' if s['prefix_caching'] else 'off'} | {s['bucket']} | {s['concurrency']} |"
            f" {s['output_tokens_per_s']:.1f} | {s['ttft_ms']['p50']:.0f} | {s['ttft_ms']['p95']:.0f} |"
            f" {s['ttft_ms']['p99']:.0f} | {s['latency_ms']['p95']:.0f} |"
            f" {'' if cost is None else f'${cost:.2f}'} |"
        )
    first = summaries[0]
    rows.append("")
    rows.append(
        f"Model {first['model']}, dtype {first['dtype']}, GPU {first['gpu']}, "
        f"max_tokens {first['max_tokens']}, commit {first['commit']}, {first['timestamp_utc']}."
    )
    return "\n".join(rows) + "\n"


def cold_start_table(cold: list[dict]) -> str:
    if not cold:
        return ""
    rows = [
        "",
        "## Cold start",
        "",
        "Time from launching the server process to the first healthy response, then the discarded"
        " warm-up pass. Neither is in the measurements above.",
        "",
        "| Engine | Prefix cache | Server ready (s) | Warm-up (s) |",
        "|---|---|---|---|",
    ]
    for c in sorted(cold, key=lambda x: (x["engine"], not x["prefix_caching"])):
        rows.append(
            f"| {c['engine']} | {'on' if c['prefix_caching'] else 'off'} |"
            f" {c['server_ready_s']:.0f} | {c['warm_up_s']:.0f} |"
        )
    return "\n".join(rows) + "\n"


def environment_block(cold: list[dict]) -> str:
    if not cold:
        return ""
    rows = ["", "## Environment", ""]
    for c in sorted(cold, key=lambda x: x["engine"]):
        if any(r.startswith(f"**{c['engine']}") for r in rows):
            continue
        rows += [
            f"**{c['engine']} {c['engine_version']}**",
            "",
            f"- GPU: {c['gpu_name']}, driver {c['driver_version']}, {c['gpu_memory_total']}",
            f"- Base image: {c['cuda_base_image']}",
            f"- torch {c['torch_version']}, dtype {c['dtype']}, max model len {c['max_model_len']},"
            f" gpu memory fraction {c['gpu_memory_fraction']}",
            f"- Model: {c['model']} revision {c['model_revision'] or 'unrecorded'}",
            f"- Server flags: `{' '.join(c['server_flags'])}`",
            "",
        ]
    return "\n".join(rows)


def chart(summaries: list[dict], path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for engine in sorted({s["engine"] for s in summaries}):
        for bucket in sorted({s["bucket"] for s in summaries}):
            points = sorted(
                (s["concurrency"], s["output_tokens_per_s"])
                for s in summaries
                if s["engine"] == engine and s["bucket"] == bucket and s["prefix_caching"]
            )
            if points:
                xs, ys = zip(*points, strict=True)
                ax.plot(xs, ys, marker="o", label=f"{engine} {bucket}")
    ax.set_xscale("log", base=2)
    ax.set_xlabel("concurrent requests")
    ax.set_ylabel("output tokens / second")
    ax.set_title(f"{summaries[0]['model']} on {summaries[0]['gpu']}")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)


def main() -> None:
    summaries, cold = load()
    (RESULTS / "summary.md").write_text(table(summaries) + cold_start_table(cold) + environment_block(cold))
    chart(summaries, RESULTS / "tokens_per_sec.png")
    print(f"wrote {RESULTS / 'summary.md'} and {RESULTS / 'tokens_per_sec.png'} from {len(summaries)} cells")


if __name__ == "__main__":
    main()
