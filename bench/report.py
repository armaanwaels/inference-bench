"""Turn the per-cell summaries in results/ into a markdown table and one chart."""

from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parents[1] / "results"
GPU_USD_PER_SECOND = {"L4": 0.000222, "A10": 0.000306}


def load() -> list[dict]:
    summaries = [json.loads(p.read_text()) for p in sorted(RESULTS.glob("*.json"))]
    if not summaries:
        sys.exit(f"no summaries in {RESULTS}; run `make bench` first")
    return summaries


def cost_per_million_output_tokens(s: dict) -> float | None:
    price = GPU_USD_PER_SECOND.get(s["gpu"])
    if not price or not s["output_tokens_per_s"]:
        return None
    return price / s["output_tokens_per_s"] * 1_000_000


def table(summaries: list[dict]) -> str:
    head = (
        "| Engine | Prefix cache | Bucket | Concurrency | Output tok/s | TTFT p50 ms | TTFT p95 ms |"
        " Latency p95 ms | $/1M output tokens |"
    )
    rows = [head, "|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(summaries, key=lambda x: (x["engine"], x["prefix_caching"], x["bucket"], x["concurrency"])):
        cost = cost_per_million_output_tokens(s)
        rows.append(
            f"| {s['engine']} | {'on' if s['prefix_caching'] else 'off'} | {s['bucket']} | {s['concurrency']} |"
            f" {s['output_tokens_per_s']:.1f} | {s['ttft_ms']['p50']:.0f} | {s['ttft_ms']['p95']:.0f} |"
            f" {s['latency_ms']['p95']:.0f} | {'' if cost is None else f'${cost:.2f}'} |"
        )
    first = summaries[0]
    rows.append("")
    rows.append(
        f"Model {first['model']}, dtype {first['dtype']}, GPU {first['gpu']}, "
        f"max_tokens {first['max_tokens']}, commit {first['commit']}, {first['timestamp_utc']}."
    )
    return "\n".join(rows) + "\n"


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
    summaries = load()
    (RESULTS / "summary.md").write_text(table(summaries))
    chart(summaries, RESULTS / "tokens_per_sec.png")
    print(f"wrote {RESULTS / 'summary.md'} and {RESULTS / 'tokens_per_sec.png'} from {len(summaries)} cells")


if __name__ == "__main__":
    main()
