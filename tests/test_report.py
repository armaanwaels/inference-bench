import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "bench"))

import report  # noqa: E402


def summary(engine="vllm", concurrency=8, bucket="short", tps=120.0, prefix=True):
    return {
        "engine": engine,
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "dtype": "bfloat16",
        "gpu": "L4",
        "bucket": bucket,
        "concurrency": concurrency,
        "prefix_caching": prefix,
        "output_tokens_per_s": tps,
        "max_tokens": 128,
        "commit": "abc1234",
        "timestamp_utc": "2026-09-22T00:00:00Z",
        "ttft_ms": {"p50": 90.0, "p95": 140.0, "p99": 180.0},
        "latency_ms": {"p95": 900.0},
    }


def test_cost_per_million_uses_the_gpu_price():
    # 100 tok/s on an L4 at $0.000222/s is $0.00000222 per token.
    assert report.cost_per_million_output_tokens(summary(tps=100.0)) == pytest.approx(2.22)
    assert report.cost_per_million_output_tokens(summary(tps=0.0)) is None
    assert report.cost_per_million_output_tokens({**summary(), "gpu": "H100"}) is None


def test_table_has_one_row_per_cell_and_records_provenance():
    text = report.table([summary(), summary(engine="sglang")])
    rows = [line for line in text.splitlines() if line.startswith("| vllm") or line.startswith("| sglang")]
    assert len(rows) == 2
    assert "commit abc1234" in text
    assert "TTFT p99 ms" in text


def test_cold_start_and_environment_are_reported_separately(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "RESULTS", tmp_path)
    (tmp_path / "vllm-short-c1.json").write_text(json.dumps(summary()))
    (tmp_path / "coldstart-vllm-pc.json").write_text(
        json.dumps(
            {
                "engine": "vllm",
                "prefix_caching": True,
                "server_ready_s": 61.0,
                "warm_up_s": 12.0,
                "server_flags": ["-m", "vllm.entrypoints.openai.api_server"],
                "engine_version": "0.20.2",
                "torch_version": "2.8.0",
                "gpu_name": "NVIDIA L4",
                "driver_version": "550.1",
                "gpu_memory_total": "23034 MiB",
                "cuda_base_image": "debian_slim (prebuilt kernels)",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "model_revision": "deadbeef",
                "dtype": "bfloat16",
                "max_model_len": 4096,
                "gpu_memory_fraction": 0.9,
            }
        )
    )
    summaries, cold = report.load()
    assert len(summaries) == 1 and len(cold) == 1  # the cold-start record is not a cell
    text = report.cold_start_table(cold) + report.environment_block(cold)
    assert "61" in text and "driver 550.1" in text and "revision deadbeef" in text


def test_load_exits_when_there_are_no_results(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "RESULTS", tmp_path)
    with pytest.raises(SystemExit):
        report.load()


def test_chart_writes_a_png(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "RESULTS", tmp_path)
    (tmp_path / "a.json").write_text(json.dumps(summary()))
    out = tmp_path / "chart.png"
    summaries, _ = report.load()
    report.chart(summaries, out)
    assert out.stat().st_size > 1000
