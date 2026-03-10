# ARCH.md

## Architecture

```
calm CLI                    calmd daemon
├ stdin detection           ├ inference backend (mlx_lm)
├ shell history context     ├ tokenizer
├ command execution         ├ KV cached prompts
└ Unix socket client        ├ candidate generation (3 samples)
                             ├ candidate scoring (heuristics)
                             └ response formatter
```

- **CLI-daemon separation**: `calm` CLI communicates with `calmd` daemon via Unix socket (`~/.cache/calmd/socket`)
- **Two modes**: Command mode (suggests runnable commands) and Analysis mode (analyzes piped stdin)

## ML/LLM Decisions

- **Backend**: `mlx_lm` for Apple Silicon inference
- **Default model**: `mlx-community/Qwen3.5-9B-OptiQ-4bit`
- **Fast model**: `mlx-community/Qwen3.5-4B-OptiQ-4bit` (fallback on OOM)
- **Thinking disabled**: Qwen 3.5 models use `enable_thinking=False`
- **Prompt length constraint**: System prompts capped at 500 tokens for efficient KV caching

## KV Cache Strategy

- Pre-fill system prompts at daemon startup into two cached states:
  - `BASE_COMMAND_STATE`
  - `BASE_ANALYSIS_STATE`
- Requests clone the appropriate state and add user query, avoiding repeated prefill
- **Max KV cache size**: 4096 tokens (configurable via `CALMD_MAX_KV_SIZE`). 
  - **Note:** Only applies to models that don't have their own cache defined. 
  - e.g. Qwen models have their own Linear + Dynamic cache implemented; they are not affected by this limit.
- **Prefix caching**: Enabled by default, can be disabled via `CALMD_DISABLE_PREFIX_CACHE=1`
- **Warmup**: Daemon runs a warmup pass at startup; skip with `CALMD_SKIP_WARMUP=1`

## Configuration (Environment Variables)

| Variable | Default | Description |
| -------- | ------- |-------------|
| `CALMD_SOCKET` | `~/.cache/calmd/socket` | Unix socket path |
| `CALMD_WAIT_TIMEOUT` | `300` | CLI wait time for daemon readiness (seconds) |
| `CALMD_MAX_KV_SIZE` | `4096` | Max KV cache size in tokens |
| `CALMD_DISABLE_PREFIX_CACHE` | `0` | Set to `1` to disable prefix caching |
| `CALMD_SKIP_WARMUP` | `0` | Set to `1` to skip daemon warmup |

## Candidate Sampling & Scoring

- Generate **3 candidates** with `temperature=0.3`, `max_tokens=96`
- Score each candidate with heuristics:
  - Valid command syntax: +3
  - Known CLI tool: +2
  - Analysis present in analysis mode: +2
  - Hallucinated flags: -3
- Select highest-scoring candidate

## Generation Parameters

| Use case | Temperature | Max tokens | Top P | Stop |
| -------- | ----------- | ---------- | ----- | ---- |
| Final output | 0.1 | 96 | 1.0 | `\n\n` |
| Candidate sampling | 0.3 | 96 | - | - |

## Performance Targets

- First token latency: < 80ms
- Full response: < 150ms

## Stdin Limits

- Max size: 64 KB
- Max lines: 200

## Safety

- Dangerous commands blocked by default (`rm -rf /`, `mkfs`, `dd if=`, `shutdown`, `reboot`)
- `--force` flag to bypass

## CLI Flags

- `-y` / `--yolo`: Auto-execute runnable command
- `-f` / `--force`: Allow dangerous commands
