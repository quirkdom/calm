# calm

`calm` is a terminal-native CLI assistant that talks to a local `calmd` daemon over a Unix socket.

## Configuration

`calm` and `calmd` read `~/.config/calm/config.toml`.
`calmd` creates that file with defaults on first start if it does not exist.
Per key precedence is: CLI flag > environment variable > config file > code default.

```toml
[common]
socket_path = "~/.cache/calmd/socket"

[cli]
wait_timeout_secs = 300
shutdown_timeout_secs = 2

[daemon]
model_path = "mlx-community/Qwen3.5-9B-OptiQ-4bit"
use_fast_model = false
verbose = false
skip_warmup = false
idle_offload_secs = 450

[backend]
disable_prefix_cache = false
max_kv_size = 4096
```

## Setup (uv)

```bash
uv sync
```

## Run daemon

```bash
uv run calmd
```

Default socket: `~/.cache/calmd/socket`
Default model: `mlx-community/Qwen3.5-9B-OptiQ-4bit`
Fast model option: `uv run calmd --fast-model` (`mlx-community/Qwen3.5-4B-OptiQ-4bit`)
Verbose debug logs: `uv run calmd --verbose` (prints raw requests, prompts, and model outputs to stderr)
Verbose mode also prints per-request inference timing (`inference_ms`) and model metadata.
If default model load hits OOM, daemon retries with the fast model automatically.

### Qwen 3.5 thinking behavior

For Qwen 3.5 models, `calmd` disables thinking mode during prompt rendering by using:

```python
tokenizer.apply_chat_template(..., enable_thinking=False)
```

This is applied only for Qwen 3.5 model paths.

## Use CLI

```bash
uv run calm "what's running on port 3567"
ps aux | uv run calm "largest memory"
```

`calm` auto-starts `calmd` if the daemon is not already running.
When model startup/download is slow, `calm` waits for daemon readiness (default timeout: 300s).

Flags:

- `-y` / `--yolo`: execute runnable command immediately
- `-f` / `--force`: allow dangerous commands

Optional env overrides:
- `CALMD_SOCKET`
- `CALMD_WAIT_TIMEOUT_SECS`
- `CALMD_SHUTDOWN_TIMEOUT`
- `CALMD_MODEL_PATH`
- `CALMD_FAST_MODEL`
- `CALMD_VERBOSE`
- `CALMD_SKIP_WARMUP`
- `CALMD_IDLE_OFFLOAD_SECS`
- `CALMD_DISABLE_PREFIX_CACHE`
- `CALMD_MAX_KV_SIZE`

## Development

```bash
uv run python -m compileall calm calmd main.py
```

### Formatting, Linting and Type Checking

```bash
uv run ruff format                      # format
uv run ruff check                       # lint
uv run ruff check --fix                 # auto-fix lint issues

uv run basedpyright                     # type check
uv run basedpyright --level error       # only errors
```
