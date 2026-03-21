# calm

<ins>**C**</ins>alm <ins>**A**</ins>nswers via (local) <ins>**L**</ins>anguage <ins>**M**</ins>odels

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
calm -y "top 5 memory processes"                # YOLO. Autoruns suggested command
calm -f "kill what's running on port 3567"      # bypass dangerous command execution protection
ps aux | calm "largest memory users"
git diff | calm "summarize what changed"
```

### Steering and Guardrails

You can force a specific output type using the `-c` (`--command`) or `-a` (`--analysis`) flags:

- **Force Command**: `calm -c "what's on port 3000"` ensures the model suggests a runnable command.
- **Force Analysis**: `calm -a "install git"` ensures the model provides an explanation instead of a command.

These flags also act as strict guardrails; if the model provides a mismatched type, the CLI will error out and refuse the output.

## Advanced Use-Cases

`calm` is context-aware. It knows your shell history, your operating system, and whether you are piping data in or out. This enables powerful "expert" workflows.

### 1. History-Aware Refinement
`calm` automatically reads your last shell command. Use it to fix syntax errors or perform follow-up actions without re-typing long paths or complex arguments.
```bash
$ docker run my-app
# (You realize you forgot to map the port)
$ calm "add port 8080 to that"
# ➜ Suggests: docker run -p 8080:8080 my-app
```

### 2. AI-Powered Git Commits
Generate high-quality, concise commit messages based on your actual staged changes.
```bash
git diff --staged | calm "summarize changes into a short commit message" | git commit -eF -
```

### 3. Log Surgical Extraction
Stop struggling with complex `grep | awk | sed` chains. Describe what you want from your logs in plain English.
```bash
tail -n 100 /var/log/system.log | calm "extract all unique process names that had a timeout error"
```

### 4. Interactive Data Transformation
Quickly transform data formats or extract specific fields for further piping.
```bash
cat users.json | calm "extract emails and join them with a semicolon"
# ➜ user1@example.com;user2@example.com;...
```

### 5. Smart Process Management & Chaining
Find and act on processes using natural language. You can even chain `calm` queries together:
```bash
calm -y "what's on port 3000" | calm -yf "kill this"
```
*(The first query suggests `lsof`, the second reads its output and suggests `kill`)*

You could also <abbr title="Keep It Simple, Stupid">KISS</abbr>:
```bash
calm -yf "kill what's on port 3000"
```

### 6. Codebase Q&A
Pipe a file to `calm` to get instant insights, bug hunts, or logic explanations.
```bash
cat main.py | calm "summarize the daemon lifecycle stages and when requests are accepted"
```

### 7. Cloud & Infrastructure
Let `calm` handle the complex CLI flags for cloud providers like AWS, GCP, or Kubernetes.
```bash
calm "list all my running EC2 instances in us-east-1 as a markdown table"
```

## What's under the hood?

Please read [ARCHITECTURE.md](ARCHITECTURE.md) or [![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/quirkdom/calm)

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
disable_prefill_completion = false
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
