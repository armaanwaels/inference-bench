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
        # modal_app.py lands in /root on its own; matrix.py has to be asked for.
        .add_local_file("bench/matrix.py", "/root/matrix.py", copy=True)
    )


# SGLang's FlashInfer backend compiles kernels at startup, so it needs nvcc from a devel base.
CUDA_DEVEL_TAG = "nvidia/cuda:12.8.1-devel-ubuntu22.04"

vllm_image = _image("vllm==0.20.2", "huggingface_hub[hf_transfer]==0.36.0")
sglang_image = (
    modal.Image.from_registry(CUDA_DEVEL_TAG, add_python="3.11")
    .apt_install("curl", "libnuma1")
    .pip_install("sglang[all]==0.5.2", "huggingface_hub[hf_transfer]==0.36.0")
    .env({"HF_HOME": "/vol/hf", "TOKENIZERS_PARALLELISM": "false"})
    .add_local_file(LOADGEN, "/usr/local/bin/loadgen", copy=True)
    .add_local_file("bench/matrix.py", "/root/matrix.py", copy=True)
)
cpu_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("huggingface_hub[hf_transfer]==0.36.0")
    .env({"HF_HOME": "/vol/hf"})
    .add_local_file("bench/matrix.py", "/root/matrix.py", copy=True)
)

app = modal.App("inference-bench")


@app.function(image=cpu_image, volumes={"/vol": vol}, timeout=60 * 60, cpu=4)
def download() -> None:
    """Pull the weights onto the volume from a CPU container, so no GPU time is spent downloading."""
    from huggingface_hub import snapshot_download

    snapshot_download(MODEL, allow_patterns=["*.json", "*.safetensors", "tokenizer*"])
    vol.commit()


def _image_check(engine: str) -> dict:
    """What a GPU container needs before it is worth paying for one."""
    import shutil

    checks = {
        "engine": engine,
        "matrix_import": MODEL,  # module level, so reaching here means matrix.py was importable
    }
    # The CPU image only downloads weights; loadgen and the engine live in the GPU images.
    if engine != "cpu":
        loadgen = shutil.which("loadgen")
        checks["loadgen_on_path"] = bool(loadgen)
        checks["loadgen_runs"] = False
        if loadgen:
            proc = subprocess.run([loadgen, "-help"], capture_output=True, text=True)
            checks["loadgen_runs"] = "-concurrency" in (proc.stdout + proc.stderr)
        cmd = _server_command(engine, prefix_caching=False)
        checks["server_command"] = cmd[-1].startswith("--")
        # Importing for real is the point: a missing .so only shows up on import.
        done = subprocess.run([sys.executable, "-c", f"import {engine}"], capture_output=True, text=True)
        error = (done.stderr or "").strip().splitlines()[-1] if done.returncode else ""
        needs_gpu = any(word in error for word in ("CUDA", "GPU", "libcuda", "nvml", "Torch not compiled"))
        checks["engine_import"] = done.returncode == 0 or needs_gpu
        if error:
            checks["engine_import_error"] = error[:200]
    checks["ok"] = all(v for k, v in checks.items() if isinstance(v, bool))
    return checks


def _environment(engine: str) -> dict:
    """Everything needed to say what produced the numbers."""
    from importlib.metadata import version

    def sh(*cmd: str) -> str:
        out = subprocess.run(cmd, capture_output=True, text=True)
        return out.stdout.strip() if out.returncode == 0 else ""

    gpu = sh("nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader").split(", ")
    revision = ""
    snapshots = Path("/vol/hf/hub") / f"models--{MODEL.replace('/', '--')}" / "snapshots"
    if snapshots.exists():
        revision = next((d.name for d in snapshots.iterdir() if d.is_dir()), "")
    return {
        "engine": engine,
        "engine_version": version(engine),
        "torch_version": version("torch"),
        "gpu_name": gpu[0] if gpu else "",
        "driver_version": gpu[1] if len(gpu) > 1 else "",
        "gpu_memory_total": gpu[2] if len(gpu) > 2 else "",
        "cuda_base_image": CUDA_DEVEL_TAG if engine == "sglang" else "debian_slim (prebuilt kernels)",
        "model": MODEL,
        "model_revision": revision,
        "dtype": DTYPE,
        "max_model_len": MAX_MODEL_LEN,
        "gpu_memory_fraction": GPU_MEMORY_FRACTION,
    }


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


def _wait_for_server(proc: subprocess.Popen, started: float, limit_s: int = 900) -> float:
    """Seconds from process start to the health endpoint answering."""
    url = f"http://127.0.0.1:{PORT}/v1/models"
    deadline = time.time() + limit_s
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"engine exited with code {proc.returncode} before serving")
        if subprocess.run(["curl", "-sf", url], capture_output=True).returncode == 0:
            return time.time() - started
        time.sleep(3)
    raise TimeoutError(f"{url} not ready after {limit_s}s")


def _loadgen_argv(engine: str, cell: dict, prefix_caching: bool, commit: str, out_dir: str, warmup: int) -> list[str]:
    return [
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
        out_dir,
        "-concurrency",
        str(cell["concurrency"]),
        "-requests",
        str(cell["requests"]),
        "-warmup",
        str(warmup),
        "-max-tokens",
        str(MAX_TOKENS),
        # Go's flag package needs the equals form for booleans: "-flag false" leaves it true.
        f"-prefix-caching={str(prefix_caching).lower()}",
    ]


def _warm_up(engine: str, prefix_caching: bool, commit: str) -> float:
    """Discarded pass over every bucket. Absorbs JIT compilation and allocator growth.

    Written to a scratch directory, so nothing here reaches results/.
    """
    started = time.time()
    scratch = "/tmp/warmup"
    Path(scratch).mkdir(parents=True, exist_ok=True)
    for bucket in ("short", "medium", "long"):
        cell = {"bucket": bucket, "concurrency": 4, "requests": 4}
        subprocess.run(_loadgen_argv(engine, cell, prefix_caching, commit, scratch, 2), capture_output=True)
    return time.time() - started


def _run_cells(engine: str, prefix_caching: bool, cells: list[dict], commit: str) -> list[dict]:
    out_dir = Path("/vol/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    env = _environment(engine)
    flags = _server_command(engine, prefix_caching)
    started = time.time()
    proc = subprocess.Popen(flags)
    summaries = []
    try:
        ready_s = _wait_for_server(proc, started)
        warmup_s = _warm_up(engine, prefix_caching, commit)
        cold_start = {
            "engine": engine,
            "prefix_caching": prefix_caching,
            "server_ready_s": round(ready_s, 1),
            "warm_up_s": round(warmup_s, 1),
            "server_flags": flags[1:],
            **env,
        }
        (out_dir / f"coldstart-{engine}-{'pc' if prefix_caching else 'nopc'}.json").write_text(
            json.dumps(cold_start, indent=2)
        )
        print(f"   ready in {ready_s:.0f}s, warm-up {warmup_s:.0f}s", flush=True)
        for cell in cells:
            argv = _loadgen_argv(engine, cell, prefix_caching, commit, str(out_dir), WARMUP)
            print("+", " ".join(argv), flush=True)
            done = subprocess.run(argv, capture_output=True, text=True)
            if done.returncode != 0:
                raise RuntimeError(f"{cell} failed: {done.stderr.strip()[:500]}")
            summary = json.loads(done.stdout)
            summary["environment"] = env
            summary["server_flags"] = flags[1:]
            # Same stem the load generator used, so this enriches its file rather than adding one.
            stem = f"{engine}-{cell['bucket']}-c{cell['concurrency']}" + ("" if prefix_caching else "-nocache")
            (out_dir / f"{stem}.json").write_text(json.dumps(summary, indent=2))
            summaries.append(summary)
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


@app.function(image=cpu_image, timeout=600)
def smoke_cpu() -> dict:
    return _image_check("cpu")


@app.function(image=vllm_image, timeout=600)
def smoke_vllm() -> dict:
    return _image_check("vllm")


@app.function(image=sglang_image, timeout=600)
def smoke_sglang() -> dict:
    return _image_check("sglang")


@app.local_entrypoint()
def smoke() -> None:
    """Build every image and check it on CPU. Costs about a cent, no GPU."""
    if not Path(LOADGEN).exists():
        raise SystemExit(f"{LOADGEN} is missing; run `make loadgen` first")
    failures = 0
    for fn in (smoke_cpu, smoke_vllm, smoke_sglang):
        report = fn.remote()
        failures += not report["ok"]
        print(f"{report['engine']:<7} {'ok' if report['ok'] else 'FAILED'}  {report}", flush=True)
    raise SystemExit(1 if failures else 0)


def _group(cells: list[Cell]) -> dict[tuple[str, bool], list[dict]]:
    grouped: dict[tuple[str, bool], list[dict]] = {}
    for c in cells:
        key = (c.engine, c.prefix_caching)
        grouped.setdefault(key, []).append({"bucket": c.bucket, "concurrency": c.concurrency, "requests": c.requests})
    return grouped


@app.local_entrypoint()
def main(confirm: bool = False, engines: str = "vllm,sglang", cache: str = "on,off") -> None:
    wanted = {e.strip() for e in engines.split(",") if e.strip()}
    variants = {c.strip() for c in cache.split(",") if c.strip()}
    cells = [c for c in matrix() if c.engine in wanted and ("on" if c.prefix_caching else "off") in variants]
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
