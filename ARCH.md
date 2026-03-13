# ARCH.md

## Architecture

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
- **Two request modes**: command mode suggests runnable shell commands; analysis mode answers questions about piped stdin.
- **Shared config**: `calm` and `calmd` read `~/.config/calm/config.toml`; `calmd` creates it on first start.

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
