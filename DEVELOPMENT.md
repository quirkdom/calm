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


## Checks

```bash
uv run python -m compileall calm calmd main.py
uv run pytest tests/test_smart_mode.py
uv run ruff format
uv run ruff check
uv run basedpyright
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
