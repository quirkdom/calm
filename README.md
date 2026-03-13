# calm 

**C**alm **A**nswers via (local) **L**anguage **M**odels

`calm` is a CLI tool that answers simple questions using a local language model. `calm` runs and communicates with the `calmd` LM server daemon.

Currently, only running **MLX** models on **Apple Silicon Macs** is supported. Please open an issue on GitHub to request other model backends and platforms.

## Quick Start

### Installation

```bash
brew install quirkdom/tap/calm  # Recommended. Easy and straightforward.

# Package managers
pipx install calm-cli
uv tool install calm-cli
python -m pip install calm-cli
```

The PyPI package name is `calm-cli`, but the installed commands are still `calm` and `calmd`.

### First run

```bash
calm "what's running on port 3567?"
```

On first run `calm` will start `calmd` in the background, which will configure itself, load models and respond to your query. This may take a while depending on your system and network speed.

### Examples

```bash
calm -f "kill what's running on port 3567"
calm -y "top 5 memory processes"
ps aux | calm "largest memory users"
git diff | calm "summarize what changed"
```

## What's under the hood?

Please read [ARCH.md](ARCH.md).

## Appendix

### Configuration

`calm` and `calmd` read `~/.config/calm/config.toml`.

`calmd` creates this file with defaults on first start if it does not exist.
Per-key precedence is: CLI flag > environment variable > config file > hardcoded default.

```toml
[common]
socket_path = "~/.cache/calmd/socket"

[cli]
wait_timeout_secs = 300
shutdown_timeout_secs = 2

[daemon]
model_path = "mlx-community/Qwen3.5-9B-OptiQ-4bit"
use_fast_model = false  # Default fast model is mlx-community/Qwen3.5-4B-OptiQ-4bit
verbose = false
skip_warmup = false
idle_offload_secs = 450

[backend]
disable_prefix_cache = false
max_kv_size = 4096
```

For the full list of environment variable overrides, local development commands, and benchmark instructions, see [DEVELOPMENT.md](DEVELOPMENT.md).

### `calmd` Auto-Start and Offload

#### Auto-start

`calm` auto-starts `calmd` if needed, preferring to start a managed service (Homebrew service or custom LaunchAgent) first. If neither managed option exists, `calm` may start an unmanaged `calmd` just to serve the request. 

This unmanaged fallback can't be administered by `calm -d`. You can always ask `calm` to help terminate the unmanaged daemon later:

```bash
> uv run calm 'terminate the calmd python daemon'
pkill -f "calmd"

Run this command? [y/N]
```

#### Offload

`calmd` automatically offloads models after periods of inactivity to save memory. This can be configured with the `idle_offload_secs` config option.

You can also manually trigger an offload using the `offload` command:

```bash
calm -d offload
```

### Running `calmd` as a login service

#### Homebrew-managed service

If installed via Homebrew, use Homebrew service management:

```bash
brew services start calm
brew services stop calm
```

When a Homebrew service is installed, plain `calm` queries will prefer that service. Use `brew services` to administer it.

#### Custom LaunchAgent managed by `calm -d`

If you installed via PyPI, `pipx`, `uv tool`, or another non-Homebrew path, you can install a per-user LaunchAgent:

```bash
calm -d install
calm -d start
```

Other useful commands:

```bash
calm -d offload
calm -d stop
calm -d uninstall
```

`calm -d install`, `start`, `stop`, and `uninstall` manage only the custom LaunchAgent created by `calm -d install`.
If a Homebrew service is installed, use `brew services` instead.

LaunchAgent logs are written to `~/Library/Logs/calmd/`.

For daemon startup diagnostics, set `CALM_DEBUG_DAEMON=1` before running `calm`. This prints `launchctl` timing and daemon start-path debug logs to stderr.
