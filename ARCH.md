# ARCH.md

## Architecture

```
calm CLI                    calmd daemon
├ stdin detection           ├ inference backend (mlx_lm)
├ shell history context     ├ tokenizer
├ command execution         ├ KV cached prompts
├ daemon control flags      ├ health + control handlers
└ Unix socket client        └ model lifecycle manager
```

- **CLI-daemon separation**: `calm` talks to `calmd` over a Unix socket (`~/.cache/calmd/socket` by default).
- **Two inference modes**: command mode suggests runnable shell commands; analysis mode answers questions about piped stdin.
- **Control path**: the same socket also handles daemon lifecycle operations such as offload and shutdown.

## Model Backend

- **Backend**: `mlx_lm` on Apple Silicon.
- **Default model**: `mlx-community/Qwen3.5-9B-OptiQ-4bit`
- **Fast model**: `mlx-community/Qwen3.5-4B-OptiQ-4bit`
- **OOM behavior**: if model load or recovery hits OOM, `calmd` retries with the fast model.
- **Thinking disabled**: Qwen 3.5 chat templating uses `enable_thinking=False`.
- **No fallback backend**: if MLX cannot load the configured model, the daemon reports the failure reason and exits.

## Prompt Cache Strategy

- `calmd` builds two base prompt states:
  - command mode system prompt
  - analysis mode system prompt
- Requests clone the appropriate base state, append request-specific prompt text, and generate from there.
- Prefix caching is enabled by default and can be disabled with `CALMD_DISABLE_PREFIX_CACHE=1`.
- `CALMD_MAX_KV_SIZE` controls prompt cache size for models that do not define their own cache behavior.

## Warmup Policy

- Normal daemon startup warms the model unless `CALMD_SKIP_WARMUP=1`.
- If `calm` auto-starts `calmd` for a waiting user query, it launches the daemon with `CALMD_SKIP_WARMUP=1` so the request is served immediately.
- Any **on-demand** load or reload skips warmup unconditionally:
  - reload after idle offload
  - reload after crash recovery
  - request-triggered initial load path while a request is waiting
- The waiting user request acts as the practical warmup for those on-demand cases.

## Auto-Offload Flow

1. `calmd` loads the model and becomes ready.
2. After each completed request, the daemon records `last_activity_at`.
3. An idle lifecycle thread waits on the daemon condition variable until either:
   - daemon state changes, or
   - the idle deadline is reached.
4. If the model is still loaded, ready, and has no active requests once the deadline passes, `calmd` unloads the model.
5. Health checks continue to report the daemon as `ready`, but with `model_status="offloaded"`.
6. A later request from `calm` notices the daemon is offloaded, prints a short wake-up message, and sends the request.
7. `calmd` reloads the model on demand, skips warmup, and answers the waiting request.

Approximate offload timing is acceptable: offload happens no earlier than the configured timeout, but not necessarily at an exact second boundary.

## Crash Recovery Flow

- Inference and warmup failures are treated as backend crashes.
- `calmd` unloads and reloads the model automatically, then retries the waiting request.
- OOM crashes switch to the fast model before retry.
- Recovery is capped at **3 attempts** to avoid infinite crash loops.
- After the third failed recovery, the daemon reports a fatal error and exits.
- The recovery counter resets after a successful request.

## Health and Control Protocol

- `mode="health"` returns daemon status such as:
  - `initializing`
  - `warming_up`
  - `ready`
  - `error`
- Health responses also include model state such as:
  - `loading`
  - `loaded`
  - `offloaded`
  - `error`
- `mode="control"` supports:
  - `action="offload"`: unload the current model without stopping the daemon
  - `action="shutdown"`: stop the daemon process

## CLI Flags

- `-y` / `--yolo`: auto-execute a runnable command
- `-f` / `--force`:
  - allow dangerous generated shell commands
  - with `-k`, request immediate daemon shutdown
- `-x` / `--offload`: ask `calmd` to offload the model
- `-k` / `--kill`: terminate `calmd`
  - graceful by default
  - if the daemon does not stop within the shutdown timeout, `calm` sends a forced shutdown request

## Environment Variables

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `CALMD_SOCKET` | `~/.cache/calmd/socket` | Unix socket path |
| `CALMD_WAIT_TIMEOUT` | `300` | How long `calm` waits for daemon readiness |
| `CALMD_SHUTDOWN_TIMEOUT` | `2` | How long `calm -k` waits before forcing shutdown |
| `CALMD_IDLE_OFFLOAD_SECS` | `900` | Idle time before model auto-offload; set `< 0` to disable |
| `CALMD_MAX_KV_SIZE` | `4096` | Max KV cache size for models without their own cache policy |
| `CALMD_DISABLE_PREFIX_CACHE` | `0` | Set to `1` to disable prefix caching |
| `CALMD_SKIP_WARMUP` | `0` | Set to `1` to skip warmup for normal daemon startup |

## Safety

- Dangerous generated shell commands are blocked by default.
- `--force` bypasses that CLI-side command safety check.
- Daemon control operations use the socket protocol rather than direct process management from the CLI.
