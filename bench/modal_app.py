"""Run the matrix on Modal: one L4, two engines, the Go load generator next to the server."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import modal

sys.path.insert(0, str(Path(__file__).resolve().parent))

from matrix import DTYPE, GPU, MAX_TOKENS, MODEL, WARMUP, Cell, estimate, matrix  # noqa: E402

MAX_MODEL_LEN = 4096
GPU_MEMORY_FRACTION = 0.90
PORT = 8000
LOADGEN = "build/loadgen-linux-amd64"

vol = modal.Volume.from_name("inference-bench", create_if_missing=True)


def _image(*packages: str) -> modal.Image:
    return (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("curl")
        .pip_install(*packages)
        .env({"HF_HOME": "/vol/hf", "TOKENIZERS_PARALLELISM": "false"})
        .add_local_file(LOADGEN, "/usr/local/bin/loadgen", copy=True)
    )


vllm_image = _image("vllm==0.20.2", "huggingface_hub[hf_transfer]==0.36.0")
sglang_image = _image("sglang[all]==0.5.2", "huggingface_hub[hf_transfer]==0.36.0")
cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface_hub[hf_transfer]==0.36.0")
    .env({"HF_HOME": "/vol/hf"})
)

app = modal.App("inference-bench")


@app.function(image=cpu_image, volumes={"/vol": vol}, timeout=60 * 60, cpu=4)
def download() -> None:
    """Pull the weights onto the volume from a CPU container, so no GPU time is spent downloading."""
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL, allow_patterns=["*.json", "*.safetensors", "tokenizer*"])
    vol.commit()


def _server_command(engine: str, prefix_caching: bool) -> list[str]:
    if engine == "vllm":
        cmd = [
            sys.executable,
            "-m",
            "vllm.entrypoints.openai.api_server",
            "--model",
            MODEL,
            "--dtype",
            DTYPE,
            "--port",
            str(PORT),
            "--max-model-len",
            str(MAX_MODEL_LEN),
            "--gpu-memory-utilization",
            str(GPU_MEMORY_FRACTION),
        ]
        return cmd if prefix_caching else cmd + ["--no-enable-prefix-caching"]
    if engine == "sglang":
        cmd = [
            sys.executable,
            "-m",
            "sglang.launch_server",
            "--model-path",
            MODEL,
            "--dtype",
            DTYPE,
            "--port",
            str(PORT),
            "--context-length",
            str(MAX_MODEL_LEN),
            "--mem-fraction-static",
            str(GPU_MEMORY_FRACTION),
        ]
        return cmd if prefix_caching else cmd + ["--disable-radix-cache"]
    raise ValueError(engine)


def _wait_for_server(proc: subprocess.Popen, limit_s: int = 900) -> None:
    url = f"http://127.0.0.1:{PORT}/v1/models"
    deadline = time.time() + limit_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"engine exited with code {proc.returncode} before serving")
        if subprocess.run(["curl", "-sf", url], capture_output=True).returncode == 0:
            return
        time.sleep(3)
    raise TimeoutError(f"{url} not ready after {limit_s}s")


def _run_cells(engine: str, prefix_caching: bool, cells: list[dict], commit: str) -> list[dict]:
    out_dir = Path("/vol/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(_server_command(engine, prefix_caching))
    summaries = []
    try:
        _wait_for_server(proc)
        for cell in cells:
            argv = [
                "loadgen",
                "-base-url",
                f"http://127.0.0.1:{PORT}",
                "-model",
                MODEL,
                "-engine",
                engine,
                "-bucket",
                cell["bucket"],
                "-gpu",
                GPU,
                "-dtype",
                DTYPE,
                "-commit",
                commit,
                "-out",
                str(out_dir),
                "-concurrency",
                str(cell["concurrency"]),
                "-requests",
                str(cell["requests"]),
                "-warmup",
                str(WARMUP),
                "-max-tokens",
                str(MAX_TOKENS),
                "-prefix-caching",
                str(prefix_caching).lower(),
            ]
            print("+", " ".join(argv), flush=True)
            done = subprocess.run(argv, capture_output=True, text=True)
            if done.returncode != 0:
                raise RuntimeError(f"{cell} failed: {done.stderr.strip()[:500]}")
            summaries.append(json.loads(done.stdout))
    finally:
        proc.terminate()
        proc.wait(timeout=120)
        vol.commit()
    return summaries


@app.function(image=vllm_image, gpu=GPU, volumes={"/vol": vol}, timeout=60 * 60, cpu=4, memory=32 * 1024)
def run_vllm(cells: list[dict], prefix_caching: bool, commit: str) -> list[dict]:
    return _run_cells("vllm", prefix_caching, cells, commit)


@app.function(image=sglang_image, gpu=GPU, volumes={"/vol": vol}, timeout=60 * 60, cpu=4, memory=32 * 1024)
def run_sglang(cells: list[dict], prefix_caching: bool, commit: str) -> list[dict]:
    return _run_cells("sglang", prefix_caching, cells, commit)


def _group(cells: list[Cell]) -> dict[tuple[str, bool], list[dict]]:
    grouped: dict[tuple[str, bool], list[dict]] = {}
    for c in cells:
        key = (c.engine, c.prefix_caching)
        grouped.setdefault(key, []).append({"bucket": c.bucket, "concurrency": c.concurrency, "requests": c.requests})
    return grouped


@app.local_entrypoint()
def main(confirm: bool = False) -> None:
    cells = matrix()
    est = estimate(cells)
    print(
        f"{len(cells)} cells on one {GPU}, about {est['total_seconds'] / 60:.1f} GPU-minutes,"
        f" estimated ${est['total_usd']:.2f}"
    )
    if not confirm:
        print("Nothing was launched. Re-run with --confirm to spend money.")
        return
    if not Path(LOADGEN).exists():
        raise SystemExit(f"{LOADGEN} is missing; run `make loadgen` first")

    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    download.remote()

    started = time.time()
    for (engine, prefix_caching), group in _group(cells).items():
        fn = run_vllm if engine == "vllm" else run_sglang
        print(f"== {engine} (prefix caching {'on' if prefix_caching else 'off'}): {len(group)} cells", flush=True)
        for summary in fn.remote(group, prefix_caching, commit):
            print(
                f"   {summary['bucket']:<6} c={summary['concurrency']:<3}"
                f" {summary['output_tokens_per_s']:.1f} tok/s"
                f" TTFT p50 {summary['ttft_ms']['p50']:.0f} ms",
                flush=True,
            )

    local = Path("results")
    local.mkdir(exist_ok=True)
    for entry in vol.listdir("results"):
        name = Path(entry.path).name
        (local / name).write_bytes(b"".join(vol.read_file(f"results/{name}")))
    print(f"pulled {len(list(local.glob('*.json*')))} files into results/ in {(time.time() - started) / 60:.1f} min")
