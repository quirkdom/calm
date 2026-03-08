# calm

`calm` is a terminal-native CLI assistant that talks to a local `calmd` daemon over a Unix socket.

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

Optional: set `CALMD_SOCKET` to override socket path.
Optional: set `CALMD_WAIT_TIMEOUT` (seconds) to change CLI wait time for daemon readiness.

## Development

```bash
uv run python -m compileall calm calmd main.py
```
