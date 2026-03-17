# Architecture

```text
calm CLI                    calmd daemon
├ query / stdin mode        ├ inference backend (mlx_lm)
├ shell history context     ├ tokenizer
├ command execution         ├ cached prompt state
├ daemon startup policy     ├ health + control handlers
├ launchd / service logic   ├ model lifecycle manager
└ Unix socket client        └ Unix socket server
```

- **CLI-daemon split**: `calm` talks to `calmd` over a Unix socket (`~/.cache/calmd/socket` by default).
- **Unified Smart Mode**: `calm` uses a single context-aware mode that determines whether to suggest a command or provide an analysis answer based on query, stdin, and shell history.
- **Shared config**: `calm` and `calmd` read `~/.config/calm/config.toml`; `calmd` creates it on first start.

## Smart Mode Logic

`calm` uses a tag-based structured output format from the model to handle different request types:

- **Contextual Prioritization**: If piped `stdin` is present, the model prioritizes answering questions directly (Analysis) rather than suggesting commands, ensuring no data is lost in the pipe.
- **Piping Awareness**: The model is aware if `stdout` is redirected (non-TTY) and prefers providing clean, concise strings suitable for further piping.
- **Steering Flags**: Users can force specific output types using `-c` (`--command`) or `-a` (`--analysis`), which act as both steering hints for the model and strict guardrails for the CLI.

## Layered Security

Command execution follows a two-layer safety check:

1. **Model Tagging**: The model evaluates the command's safety in context and provides a `[SAFE: YES|NO]` tag.
2. **Hardcoded Checks**: The CLI runs a static regex check for known dangerous tokens (e.g., `rm -rf`, `mkfs`).

If *either* check flags a command as unsafe, the CLI requires the `-f` (`--force`) flag to execute.

## Daemon Administration Model

There are three possible daemon modes:

1. **Homebrew-managed service**
2. **Custom LaunchAgent installed via `calm -d install`**
3. **Unmanaged background daemon**

### What `calm -d` administers

- `calm -d install`, `start`, `stop`, and `uninstall` administer only the custom LaunchAgent path.
- If a Homebrew service is detected, `calm -d install` refuses and tells the user to use `brew services`.
- `calm -d start` requires the custom LaunchAgent to exist. If an unmanaged daemon is currently serving the socket, it is stopped first to avoid duplicate daemons.
- `calm -d offload` remains daemon-agnostic because it is model-state control over the socket, not service installation.

### What plain `calm` queries do

When a query arrives and no daemon is currently ready, `calm` tries startup in this order:

1. Homebrew service, if detected
2. Custom LaunchAgent, if detected
3. Unmanaged detached `calmd` as a fallback

This keeps regular query handling resilient, while keeping explicit daemon administration simpler and limited to the custom LaunchAgent path.

## Warmup Policy

- Normal daemon startup warms the model unless `CALMD_SKIP_WARMUP=1`.
- Query-triggered auto-start skips warmup so the waiting request is served as quickly as possible.
- That applies to both:
  - unmanaged detached startup
  - managed launchd startup triggered on demand by `calm`
- Reload after idle offload or crash recovery also skips warmup.

The waiting user request acts as the practical warmup in those on-demand cases.

## Auto-Offload Flow

1. `calmd` loads the model and becomes ready.
2. After each completed request, the daemon records `last_activity_at`.
3. A lifecycle thread waits for either state changes or the idle timeout.
4. If the daemon is still idle when the timeout expires, `calmd` unloads the model.
5. Health checks continue to report the daemon as reachable, but with `model_status="offloaded"`.
6. A later request causes `calmd` to reload on demand and answer the waiting request.

## Crash Recovery Flow

- Inference and warmup failures are treated as backend crashes.
- `calmd` unloads and reloads the model automatically, then retries the waiting request.
- OOM crashes switch to the fast model before retry.
- Recovery is capped at **3 attempts**; after that the daemon reports a fatal error and exits.

## Health and Control Protocol

- `mode="health"` returns status such as `initializing`, `warming_up`, `ready`, or `error`.
- Health responses also include model state such as `loading`, `loaded`, `offloaded`, or `error`.
- `mode="control"` supports:
  - `action="offload"` to unload the current model without stopping the daemon
  - `action="shutdown"` to stop the daemon process

## Environment Notes

- `CALMD_SOCKET` controls the Unix socket path.
- `CALMD_SKIP_WARMUP` is used internally for query-triggered startup and can also be set manually.
- `CALM_DEBUG_DAEMON=1` enables CLI-side launchd timing diagnostics.

See [DEVELOPMENT.md](DEVELOPMENT.md) for the full env var list.
