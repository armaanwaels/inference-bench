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


def test_loadgen_argv_uses_the_equals_form_for_booleans():
    # "-prefix-caching false" would leave the flag true and overwrite the cached run's files.
    import modal_app

    argv = modal_app._loadgen_argv(
        "vllm", {"bucket": "short", "concurrency": 32, "requests": 64}, False, "abc1234", "/tmp", 4
    )
    assert "-prefix-caching=false" in argv
    assert "false" not in [a for a in argv if not a.startswith("-prefix-caching")]
