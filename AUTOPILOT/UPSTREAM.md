# Upstream issues this work could help with

Candidate open issues in vLLM and SGLang. The autopilot only reads. It never comments, reacts,
opens an issue or pull request, forks or stars, and it never writes the upstream patch. Armaan
chooses the issue, writes the patch and submits it himself.

**Dec 17, 2026 rule:** from that date, if this file has no issue with a reproduction, the top of
`LOG.md` says so.

## Status on Nov 27, 2026

Slice 2 (Scout 1) read both contribution guides, the two lead issues, and the pinned engine
releases. Result:

- One candidate, vLLM 27433 (the "model coverage" part). Its steps are exact commands, taken from
  upstream's own test suite. Nobody has run them for this project yet. It is a validation run, not
  a reproduction of a defect.
- No candidate yet that reproduces a defect. Finding one is the job of slice 9 (Scout 2). The
  leads for it are listed below.
- The SGLang lead, issue 10278, is closed. SGLang has no candidate yet.

A reproduction that needs a GPU can be run by the GPU workflow (see "GPU runs" in `PLAN.md`),
under the same budget and one request per day rules. The result file path is then recorded with
the candidate.

## What the two projects ask of a contributor

Read on Nov 27, 2026. These are the rules Armaan's own patch has to meet. They are summarised
here so he does not have to find them again. Quoted text is copied from the pages.

### vLLM

Sources: https://docs.vllm.ai/en/latest/contributing/ and
https://github.com/vllm-project/vllm/blob/main/AGENTS.md

- **Sign-off.** Every commit needs a `Signed-off-by:` line (the DCO). `git commit -s` adds it.
- **AI use.** The guide does not ban AI help. It bans pull requests with no human behind them:
  "Do not submit "pure agent" PRs. The human submitter is responsible for reviewing all changed
  lines, validating behavior end-to-end, and running relevant tests." AGENTS.md says the same more
  sharply: "Pure code-agent PRs are **not allowed**. A human submitter must understand and defend
  the change end-to-end." It adds that breaking its rules "can result in automatic banning".
  When AI tools gave real help, the pull request must say so in its description, and the commits
  must carry a trailer such as `Co-authored-by:`.
  The rule for this project is stricter than the guide: the autopilot writes no part of the
  upstream patch. Armaan writes it.
- **What an AI-assisted pull request description must contain** (AGENTS.md): why it does not
  duplicate an open pull request, the test commands that were run with the exact pytest summary
  line, model evaluation results when output or serving changes, and a clear statement that AI
  help was used.
- **Check for duplicates first.** AGENTS.md lists the searches to run before proposing a change
  (open pull requests that mention the issue number, and by keywords).
- **No busywork.** One-off pull requests for a typo or a style fix are not wanted.
- **Tests.** "Include sufficient tests to ensure the project stays correct and robust." Fixes to
  behaviour a user can see need a test through a real entry point (`LLM` or the OpenAI server).
  No one-off kernel benchmarks under `tests/`.
- **Docs.** A change a user can see must update the rendered docs in the same pull request.
- **Title.** Bracketed tags first, for example `[Bugfix][Scheduler] Fix priority handling`.
  `[Doc]` or `[Docs]` for documentation.
- **Size.** More than 500 changed lines of architecture needs an RFC issue first.
- **Limit.** A contributor without write access may have at most 6 open pull requests.
- **CI.** Upstream CI does not start by itself on a new contributor's pull request. A reviewer
  starts it. The guide says not all unit tests pass on CPU, so local CPU runs are not enough.

### SGLang

Source: https://docs.sglang.io/docs/developer_guide/contribution_guide

- **Fork and branch.** New contributors work from a fork, on a branch, never on `main`.
- **Formatting.** `pre-commit run --all-files` must pass before the pull request is opened.
- **Tests.** Unit tests live under `test/registered/unit/` and mirror the source tree. Tests
  registered for CI must use `CustomTestCase`. Tests that need a server follow
  `test/registered/README.md`.
- **Accuracy.** "If your code changes model output, run an accuracy evaluation appropriate for
  the affected model and feature." The guide's own example is a GSM8K run, and it warns that this
  check "can have significant variance (1%-5%) in accuracy due to batching and the
  non-deterministic nature of the inference engine". (The range is written with a dash on the
  page.)
- **Title.** `[Type] scope: title`, checked by CI. Types: `Feat`, `Fix`, `Refactor`, `Perf`,
  `Doc`, `Test`, `CI`, `Chore`, `Misc`.
- **Review.** Approval from the Merge Oncall and the code owner, as described in
  `.github/MAINTAINER.md` (not read yet).
- **CI.** Only trusted contributors can start CI. A new contributor needs someone with permission
  to do it.
- **AI use and sign-off.** The page read has no section on AI-written changes and does not
  mention a sign-off line. That is what the page says today, not proof that no rule exists
  elsewhere in the repository. The repository has an `.agents/skills` folder, not read yet.
  Slice 9 checks `.github/MAINTAINER.md` and the pull request template.

## Engine versions and their deterministic modes

Checked on Nov 27, 2026 against the release files on PyPI, not against memory.

| | vLLM | SGLang |
|---|---|---|
| Pinned in this repository | 0.20.2 | 0.5.2 |
| Pin released on PyPI | May 10, 2026 | Sep 11, 2025 |
| Newest release on PyPI on Nov 27, 2026 | 0.34.0 (Nov 16, 2026) | 0.5.23 (Oct 30, 2026) |
| Deterministic mode | `VLLM_BATCH_INVARIANT=1` | `--enable-deterministic-inference` |
| Does the pin have it | Yes | **No** |

**vLLM 0.20.2.** The source archive on PyPI has the setting in `vllm/envs.py`, a docs page
(`docs/features/batch_invariance.md`) and a test suite (`tests/v1/determinism/`). Three things
about the L4, which is an Ada Lovelace card with compute capability 8.9 (NVIDIA's table at
https://developer.nvidia.com/cuda/gpus):

- The 0.20.2 docs page says: "Batch invariance currently requires NVIDIA GPUs with compute
  capability 9.0 or higher", and names H100, H200, B100 and B200. The L4 is not on that list.
- The 0.20.2 code has a path for capability 8.x all the same
  (`enable_batch_invariant_mode` treats family 80 like family 100), and its test helper says:
  "Supports testing on Ampere and Ada Lovelace devices. Note: For devices with SM < 90, batch
  invariance does not support CUDA Graphs."
- The current docs page (https://docs.vllm.ai/en/stable/features/batch_invariance/, which is
  0.34.0) says "NVIDIA GPUs with compute capability 8.0 or higher".

So on the pin the mode exists, and whether it holds on an L4 is not promised by that version's
docs. That is a question the correctness run can answer with a result file. Nothing is claimed
here about the answer. `Qwen/Qwen2.5-7B-Instruct`, the model this repository uses, is on the
tested models list of both the 0.20.2 page and the current page.

**SGLang 0.5.2.** The wheel on PyPI has no match for `enable_deterministic_inference` or
`batch_invariant` in any Python file. The flag is not in 0.5.3rc0 (Sep 15, 2025) either. The
first final release with it is 0.5.3 (Oct 6, 2025). In 0.5.3 the mode accepts the attention
backends `flashinfer`, `fa3` and `triton`, turns the radix cache off unless the backend is `fa3`,
and forces the sampling backend to `pytorch`. 0.5.3 also ships
`python3 -m sglang.test.test_deterministic --n-trials <n> --test-mode <single|mixed|prefix>`,
which sends the same prompt in random batch sizes to a running server and counts unique outputs.
Later releases were not opened today, so what the mode accepts in 0.5.23 is not recorded yet.

**What follows for this project.** The SGLang half of the correctness suite cannot test a
deterministic mode on the pin. PLAN.md slice 20 now says how this is handled. Also worth
knowing: the two pins are eight months apart in age, so the existing one-run-per-cell comparison
is between a May 2026 vLLM and a September 2025 SGLang.

## How a candidate is recorded

```
### <engine> #<number>: <title as shown>

- Link:
- Status as seen, and the date seen: (open or closed, labels, assignee, last activity)
- Why it fits: (which part of this repository exercises it)
- Reproduction steps: (exact commands; say whether they need a GPU)
- Reproduction run by: (nobody yet / the GPU workflow on <date> / Armaan on <date>, with the
  result file path)
- What a fix or contribution would need: (tests the maintainers ask for, files likely involved)
- Notes from the thread: (what maintainers asked for; facts only)
```

A candidate counts as "with a reproduction" when its steps are exact commands that someone can
run without guessing. Whether the steps were actually run, and by whom, is recorded separately.

## Candidates

### vLLM #27433: [Feature]: Batch Invariant Feature and Performance Optimization (the "Model coverage" part)

- Link: https://github.com/vllm-project/vllm/issues/27433
- Status as seen, and the date seen: open on Nov 27, 2026. Opened Oct 23, 2025. Labels
  `batch-invariance`, `feature request`, `good first issue`. Four assignees (bwasti, PaulZhang12,
  yewentao256, sfeng33). 107 comments, last updated Nov 25, 2026. The issue body is a checklist.
  Unchecked on Nov 27: "FLASHINFER_MLA support" (help needed, waits on a FlashInfer issue),
  "Optimize the batch invariant performance" (help needed), and under "Nice to have": "Prefix
  caching support", AMD support, XPU support, speculative decoding support. Below the checklist:
  "Model coverage ... Help needed for validations of more models. 1. Test a model using the script
  in https://github.com/vllm-project/vllm/tree/main/tests/v1/determinism 2. Submit a PR updating
  the document".
- Why it fits: the maintainers ask for exactly the kind of run this project is set up to make: one
  model, one GPU, same request alone and inside a batch, outputs compared. The correctness suite
  (PLAN.md Part D) makes the same comparison over HTTP. The L4 (capability 8.9) is the cheap end
  of the supported range, and recent comments on the thread report validations on other 8.x cards
  (an RTX 4090 on Oct 14, 2026, an A100 on Oct 23, 2026), each followed by a small docs pull
  request (61575, 63348). The contribution is a docs change with evidence, which a first-time
  contributor can write by hand.
- Limits of the fit, stated plainly: upstream already has the test suite, including an HTTP test
  (`test_online_batch_invariance.py`), so this repository's suite is a second, independent check
  and not a new idea. `Qwen/Qwen2.5-7B-Instruct` is already on the tested list, so validating it
  again adds no line to the docs. A contribution needs a model that is not on the list and fits in
  the L4's 24 GB. Choosing it is Armaan's call. The list is at
  https://docs.vllm.ai/en/latest/features/batch_invariance/#tested-models
- Reproduction steps (need a GPU with compute capability 8.0 or higher; written from the vLLM
  contribution guide and AGENTS.md as read on Nov 27, 2026):

  ```
  git clone https://github.com/vllm-project/vllm.git
  cd vllm
  uv venv --python 3.12 --seed --managed-python
  source .venv/bin/activate
  VLLM_USE_PRECOMPILED=1 uv pip install -e .
  vllm download-kernels
  uv pip install -r requirements/test/cuda.in
  .venv/bin/python -m pytest tests/v1/determinism/test_batch_invariance.py -v
  ```

  The first five lines are the contribution guide's install for Python-only work. The test
  dependency line and the pytest form are from AGENTS.md. The two pages differ in small ways (the
  guide installs test dependencies from `requirements/common.txt` and `requirements/dev.txt`), so
  if the sixth line fails, the guide's form is the fallback:
  `uv pip install -r requirements/common.txt -r requirements/dev.txt --torch-backend=auto`.
  None of this has been run for this project.

  With no model set, the suite uses `Qwen/Qwen3-1.7B` (the default in
  `tests/v1/determinism/utils.py` on `main`, read Nov 27, 2026). That model is already on the
  tested list, so this first run only shows whether the suite passes on an L4. For a model that
  is not on the list, the last line becomes:

  ```
  VLLM_TEST_MODEL=<model id> .venv/bin/python -m pytest tests/v1/determinism/test_batch_invariance.py -v
  ```

  The suite turns batch invariant mode on by itself (`conftest.py`). On `main` it runs each test
  once per attention backend: `FLASH_ATTN`, `TRITON_ATTN` and `FLEX_ATTENTION` on CUDA. Expected
  output: the pytest summary line. A validation counts when every test passes. In 0.20.2 the test
  file reads these settings from the environment, which matter on a 24 GB card:
  `VLLM_NEEDLE_BATCH_SIZE` (default 128), `VLLM_GPU_MEMORY_UTILIZATION` (default 0.5),
  `VLLM_MAX_MODEL_LEN` (default 5120). The test file on `main` was not read today, so the names
  on `main` are to be confirmed in slice 9.
- Reproduction run by: nobody yet. The GPU workflow cannot run these steps as written, because it
  runs this repository's Modal entry points and not upstream's pytest suite. Slice 21 decides
  whether to add an entry point for it or to leave the run to Armaan.
- What a fix or contribution would need: a pull request titled with `[Doc]` or `[Docs]` that adds
  the model to the tested models list in `docs/features/batch_invariance.md`, with the GPU, the
  dtype, the test command and the exact pytest summary line in the description, a
  `Signed-off-by:` line, and a note on AI help if any was used. A check first that no open pull
  request already adds the same model.
- Notes from the thread: 15 of the 107 comments were visible in the page read today, the first
  ones and the last ones. In them, people who validated a model posted the GPU, the dtype and the
  pass count, then linked a docs pull request. A comment from Oct 4, 2026 reports that a model on
  the tested list no longer started in batch invariant mode after a later change, which suggests
  the list can go stale and that a failing validation is as useful to the maintainers as a
  passing one. The middle of the thread has not been read.

## Leads for slice 9 (Scout 2), not yet read

Seen by title only on Nov 27, 2026, in the vLLM list of open issues with the label
`batch-invariance` (60 open, 8 closed; only the newest 25 were shown) or mentioned in the 27433
thread. None of them has been opened. They are listed because the title suggests the problem
could show on one L4 with a small dense model. Each needs its status, its model and its GPU
checked before it can become a candidate.

- vLLM 27433, the unchecked item "Prefix caching support". This repository already runs vLLM with
  prefix caching on and off, so "is the output the same with the cache on, in batch invariant
  mode" is a question the correctness suite can ask directly. What exactly is missing upstream is
  not stated in the part of the thread read today.
- vLLM 59086: "VLLM_BATCH_INVARIANT=1 is not batch-invariant for AWQ models on sm8x in the default
  mode". The L4 is an 8.x card. The thread says pull request 60479 addresses it. Status not
  checked. https://github.com/vllm-project/vllm/issues/59086
- vLLM 58899: "Greedy output changes between restarts, also with VLLM_BATCH_INVARIANT=1: the
  q/k-norm + RoPE combo kernel picks its reduction config by timing". Opened Sep 27, 2026.
  https://github.com/vllm-project/vllm/issues/58899
- vLLM 58973: "V2 speculative prefill can change Qwen3-4B's first greedy token through RMSNorm
  autotune configuration". Opened Sep 28, 2026. A 4B model fits on an L4.
  https://github.com/vllm-project/vllm/issues/58973
- vLLM 67275: "[RFC][Performance] Generic batch-size-aware matmul configs for untuned
  batch-invariant shapes". Opened Nov 12, 2026. Might want throughput numbers from more GPU
  types. https://github.com/vllm-project/vllm/issues/67275
- vLLM 67696: "[RFC]: CPU Backend support for VLLM_BATCH_INVARIANT=1". Opened Nov 14, 2026. The
  author already has a prototype. https://github.com/vllm-project/vllm/issues/67696
- SGLang 50045: "SGLang 1.0 Release Tracker". Seen only as a search result snippet. The snippet
  describes release work on malformed requests to the OpenAI-compatible routes getting a 4xx
  answer, with a fuzz test in pull request 50753. Not opened.
  https://github.com/sgl-project/sglang/issues/50045
- SGLang has no open tracking issue for deterministic inference (see "Dropped"). Slice 9 has to
  search the SGLang tracker by words (determinism, temperature 0, seed, radix cache, usage in
  streaming), not by label.

## Dropped

- **SGLang 10278: [Feature] Support deterministic inference with Batch Invariant Ops.**
  https://github.com/sgl-project/sglang/issues/10278 Seen Nov 27, 2026: closed as completed on
  Feb 20, 2026 by the inactivity bot, no assignee, labels `deterministic` and `enhancement`, all
  three sub-issues closed. The checklist in its body still shows unfinished items (for example
  radix cache support with FlashInfer, and speculative decoding), but a closed roadmap is not an
  open issue to help with. Kept here as background: it links the pull requests that built the
  mode (10645, 10678, 10694, 10651) and the test module `sglang.test.test_deterministic`.
- **SGLang 38695: [Feature] Unify the MoE router GEMM behind one gate layer.**
  https://github.com/sgl-project/sglang/issues/38695 Seen by title on Nov 27, 2026: the only open
  issue with the label `deterministic`, opened Sep 9, 2026, with a linked pull request (49668).
  Dropped by title: it is a refactor of mixture-of-experts code that already has a pull request,
  and this repository tests one dense model.
