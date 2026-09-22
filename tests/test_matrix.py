import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

import matrix  # noqa: E402


def test_matrix_shape():
    cells = matrix.matrix()
    assert len(cells) == 21  # 2 engines x 3 concurrencies x 3 buckets, plus 3 prefix-cache-off cells
    assert {c.engine for c in cells} == {"vllm", "sglang"}
    off = [c for c in cells if not c.prefix_caching]
    assert len(off) == 3
    assert all(c.engine == "vllm" and c.concurrency == 32 for c in off)


def test_engine_starts_counts_distinct_configurations():
    assert matrix.engine_starts(matrix.matrix()) == 3


def test_estimate_stays_inside_the_budget():
    est = matrix.estimate(matrix.matrix())
    assert est["total_seconds"] / 60 < 30
    assert est["total_usd"] < 20
    assert est["total_usd"] == est["gpu_usd"] + est["cpu_and_memory_usd"]
