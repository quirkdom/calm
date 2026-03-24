# DEVELOPMENT.md

## Local Setup

```bash
uv sync
```

## Running Locally

Run the daemon directly:

```bash
uv run calmd
```

Run the CLI:

```bash
uv run calm "what's running on port 3567"
ps aux | uv run calm "largest memory users"
```

Useful daemon options:

- `uv run calmd --fast-model`
- `uv run calmd --verbose`

## Environment Variables

Runtime overrides:

### Calm CLI
- `CALMD_SOCKET`
- `CALMD_WAIT_TIMEOUT_SECS`
- `CALMD_SHUTDOWN_TIMEOUT`
- `CALM_DEBUG_DAEMON`

`CALM_DEBUG_DAEMON=1` prints CLI-side launchd timing and daemon startup diagnostics to stderr.

### Calm Daemon
- `CALMD_SOCKET`
- `CALMD_MODEL_PATH`
- `CALMD_FAST_MODEL`
- `CALMD_VERBOSE`
- `CALMD_SKIP_WARMUP`
- `CALMD_IDLE_OFFLOAD_SECS`
- `CALMD_DISABLE_PREFIX_CACHE`
- `CALMD_MAX_KV_SIZE`
- `CALMD_DISABLE_PREFILL_COMPLETION`
- `CALMD_ENABLE_THINKING`

## Checks

```bash
uv run python -m compileall calm calmd
uv run ruff format
uv run ruff check
uv run basedpyright
```

## Evals

```bash
uv run pytest tests/eval_*.py
```

If you need to print debug output:

```bash
uv run pytest tests/eval_*.py --vv -s       # all debug output
uv run pytest tests/eval_*.py -ra           # only for non-passing tests
```

## Benchmarks

Run the benchmark driver:

```bash
uv run python benchmarks/bench.py
```

Useful options:

- `uv run python benchmarks/bench.py --help`
- `uv run python benchmarks/bench.py --enable-longtail`
- `uv run python benchmarks/bench.py --socket /tmp/calmd-bench.sock`
- `uv run python benchmarks/bench.py --log-dir benchmarks/logs`

Benchmark reports are written under `benchmarks/logs/` with timestamped filenames.

## Architecture

Please refer to [ARCHITECTURE.md](ARCHITECTURE.md)

## Release

### PyPI

```bash
uv build
uv publish
```

> [!TIP]
> Manual release to indices is not recommended. Please rely on the GHA [release](.github/workflows/release.yml) workflow instead.

### Homebrew

> [!CAUTION]
> Ensure that the current package version is released and available on PyPI.

To regenerate the Homebrew formula for `calm`:

1. Navigate to the `packaging/homebrew` directory.
2. Run the generation script:
   ```bash
   uv run generate-calm-formula.py > calm.rb
   ```
3. Test the formula locally:
   ```bash
   HOMEBREW_DEVELOPER=1 brew install --build-from-source ./calm.rb
   ```
4. To update the official tap, copy `calm.rb` to [quirkdom/homebrew-tap](https://github.com/quirkdom/homebrew-tap) under `Formula/calm.rb`.
